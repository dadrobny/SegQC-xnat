# Item 109 — Magnitude-sensitive per-mode attribution

> **Created:** 2026-08-12 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 26 — Carried-Defect Remediation (pre-real-data)
> **Queue:** [`../queue/queue-016.md`](../queue/queue-016.md) · Item 109
> **Objectives:** G7
> **Suggested branch:** `aide/109-magnitude-sensitive-attribution`

---

## Description

Repair run-vs-run mode attribution in
`src/segfacet/eval/per_mode_cohort.py`, where
`normalised_delta = delta / max(|value_a − baseline|, |value_b − baseline|)`
saturates to exactly ±1.0 whenever either run sits on its metric's baseline.
Seven of the eight `PER_MODE_METRIC_SPECS` baselines are `0.0`, so any
comparison in which two or more modes return to baseline ties at 1.0 across all
of them, and `attributed_mode` is then decided by the documented lowest-mode
tie-break rather than by which mode actually moved further. Stage 18's
run-vs-run **attribution** deliverable does not do what its own docstring
claims, and two of item 101's own tests demonstrate the trap on deliberately
different-magnitude inputs.

The fix is **not** a single universal scale. Two project-wide rules govern
which metrics may be scaled at all:

1. **No normalisation factor may introduce a supervision dependency.** Anything
   derived from ground truth — a GT label count, "the levels this scan *should*
   have", a reference annotation — is supervision, not a feature. Scaling by it
   yields a number that cannot be computed on real segmenter output, the setting
   FACET exists to analyse, and mixes supervision into the feature space. This
   holds even for metrics that are themselves defined as a candidate-vs-GT
   comparison: that a metric *needs* GT does not license its **scale** to import
   further GT-derived quantities.
2. **Normalisation is human-reviewed, or it does not happen.** The sole
   exception is a scaling intrinsic by construction — already dimensionless, or
   bounded 0..1 with a derivable full swing, where the denominator falls out of
   the metric's own definition and no judgement is exercised. Everything else
   needs an explicitly reviewed, recorded constant or threshold. **The default,
   absent review, is no normalisation.**

Applied to the eight metrics:

- **Intrinsic — scaled automatically.** `unanchored_foreground_fraction`
  (baseline 0.0), `min_dominant_component_fraction` (baseline 1.0, decreasing),
  `mislabelled_volume_fraction` (0.0) and the other fraction-valued entries are
  mathematically confined, so the distance from baseline to the far end of the
  range is derivable with no free parameter and no supervision.
- **Raw by default.** `rogue_island_count` is a *maximum over per-label
  entries*, so a scan-level denominator would change the quantity rather than
  scale it. `missing_level_count` is scan-level, but its only natural
  denominator — the levels the scan was expected to contain — is GT-derived and
  therefore barred by rule 1. Both report raw with `normalised_delta = None`.
- **Reviewed threshold, opt-in, none set here.** For rogue islands the clean
  expectation is *none*, which makes a small declared threshold the plausible
  candidate; the value is **TBC**. This item ships the mechanism and the review
  requirement, and declares nothing.

**In scope.** The normalisation and attribution logic, the optional per-metric
excursion field, and the affected rendering and tests.

**Not in scope.** New metrics; changing any metric's definition, baseline or
direction; `eval/per_mode.py`'s computation (item 112 owns the only authorised
change there); neighbourhood-relative normalisation (logged as backlog, see
Decisions).

## Acceptance Criteria

- [ ] **AC1: bounded metrics scale by their derivable full swing.** For a
  metric confined to a known range, `normalised_delta` is `delta` divided by the
  distance from `baseline` to the far end of that range, and the divisor is
  derived from the metric's declaration, not hand-entered.
- [ ] **AC1b: no scale depends on supervision.** No metric's divisor is derived
  from ground truth, a reference annotation, or any other supervision signal —
  including for metrics whose own `source` is `candidate_vs_gt`. A test asserts
  this for every metric that carries a scale.
- [ ] **AC2: everything else is raw by default.** `normalised_delta is None` for
  any metric without an intrinsic scale or a reviewed declared threshold —
  `rogue_island_count` and `missing_level_count` today — and the raw delta
  remains available on the same record.
- [ ] **AC3: a reviewed threshold may be declared.** `MetricSpec` gains an
  optional reference-excursion field, unset for every metric by default; when
  set, that metric scales by it. The field's docstring states that setting it is
  a human-review decision requiring a recorded rationale, not a tuning knob.
- [ ] **AC4: no threshold is set in this item.** Every shipped `MetricSpec`
  leaves the new field unset — the mechanism exists, the judgement is not made
  here.
- [ ] **AC5: attribution follows magnitude.** Given two modes whose normalised
  deltas differ, `attributed_mode` is the larger one regardless of mode number.
- [ ] **AC6: baseline no longer saturates.** For a bounded metric where one run
  sits exactly on baseline, `|normalised_delta| < 1.0` unless the other run sits
  at the far end of the range.
- [ ] **AC7: the differential case works.** With mode A moving 0.1 and mode B
  moving 0.9 from a shared baseline on comparably-bounded metrics, attribution
  is B.
- [ ] **AC8: unnormalisable modes are excluded from attribution, visibly.**
  Attribution ranks only metrics carrying a `normalised_delta`; the result
  records which modes were excluded and why, so a reader is never left to assume
  they were considered and lost.
- [ ] **AC9: no-attribution is explicit.** When no metric carries a
  `normalised_delta`, `attributed_mode is None` with a stated reason — never a
  fallback to the lowest mode.
- [ ] **AC10: the tie-break is last-resort only.** The lowest-mode tie-break
  applies only on an exact equality of normalised deltas, and a test pins that
  it is not reached in the AC7 scenario.
- [ ] **AC11: unchanged where it was already right.** For comparisons where
  neither run sits on baseline, every previously-reported `normalised_delta`
  and `attributed_mode` is unchanged.
- [ ] **AC12: the report says what it means.** `eval/report.py`'s rendering
  distinguishes "not normalisable" from "normalised to 0.0", and item 101's
  docstring in `per_mode_cohort.py` is updated to describe the new rule.

## Assumptions

- **The classification is recorded per metric, not inferred from its name.**
  Name-based inference (`*_fraction` scalable, `*_count` not) happens to give
  the right answer today, but for the wrong reason — the deciding questions are
  whether the scale is intrinsic and whether it stays free of supervision, not
  what the metric is called. Each of the eight metrics carries an explicit,
  reviewed class.
- **A metric may use GT even though its scale may not.** Four of the eight are
  `source: "candidate_vs_gt"` by item 099's design, which this item does not
  change. The supervision rule constrains the **divisor**, not the metric.
- **`PER_MODE_METRIC_SPECS` may gain an optional field.** Additive only —
  existing field names, values, baselines and directions are untouched, so
  item 104's catalogue and any consumer reading the specs keep working.
- **`eval/per_mode.py` is not modified by this item.** The classification lives
  with the spec declaration; if that requires touching `per_mode.py`, hand back
  and coordinate with item 112 rather than both editing it.
- **Two-run comparison is the primary use case.** Cohort-range normalisation was
  rejected precisely because a run-vs-run comparison is a cohort of two, where
  the observed range equals `|delta|` and every mode re-saturates to 1.0.

## Implementation Steps

1. Classify each of the eight metrics as bounded (with its full swing) or
   unbounded, and record the classification where the specs are declared.
2. Add the optional reference-excursion field to `MetricSpec`, defaulting unset.
3. Rewrite the scale computation: full swing for bounded, declared excursion if
   set, otherwise `None`.
4. Rewrite attribution to rank only over entries with a `normalised_delta`,
   record exclusions, and return `None` with a reason when the set is empty.
5. Confine the lowest-mode tie-break to exact equality.
6. Update `eval/report.py` rendering and the module docstring.
7. Update item 101's affected tests to the new semantics, preserving their
   original intent (they were written to demonstrate differential attribution —
   they should now pass for the reason they were written).

## Testing Strategy

New module `tests/test_109_attribution_scale.py`, plus updates to
`tests/test_101_per_mode_cohort.py` where its ACs pinned the old behaviour:

- AC1/AC2: one test per metric class, asserting divisor provenance.
- AC1b: for every metric carrying a scale, assert the divisor is a function of
  the metric's own declaration only — computing a comparison twice with two
  different GT inputs but identical candidates must yield the same divisor.
- AC5/AC7: the differential fixture (0.1 vs 0.9 from a shared baseline).
- AC6: one run exactly on baseline, assert `< 1.0`.
- AC8/AC9: a comparison over unbounded metrics only — `attributed_mode is
  None`, exclusions listed.
- AC10: exact-equality fixture, assert the tie-break fires there and nowhere
  else.
- AC11: a comparison with both runs off baseline, values pinned to the
  pre-change output.
- AC3/AC4: assert the field exists, and that every shipped spec leaves it unset.

Adversarial: both runs identical (all deltas 0.0); a metric value of `None`
(absent from a record); a bounded metric already at the far end of its range in
both runs; NaN/inf guards.

## Validation

Construct two synthetic runs — a large mode-2 move and a small mode-3 move —
and run the run-vs-run comparison through the CLI path item 101 added. Confirm
the report attributes mode 2, names mode 3's exclusion or lower rank explicitly,
and that reversing the magnitudes reverses the attribution. Paste both outputs
into Decisions.

## Dependencies

None blocking. Coordinates with item 112, which owns the only authorised change
to `eval/per_mode.py`.

## Authorised paths

- `src/segfacet/eval/per_mode_cohort.py`
- `src/segfacet/eval/report.py`
- `tests/test_109_attribution_scale.py`
- `tests/test_101_per_mode_cohort.py`
- `docs/aide/items/109-magnitude-sensitive-attribution.md`

## Decisions & Trade-offs

- **Two rules decide scaling: no supervision in the divisor, and review or
  don't scale** (maintainer, 2026-08-12). The design arrived here in three
  steps, and both intermediate positions were wrong:
  1. A blanket case-intrinsic denominator for counts was rejected — dividing a
     per-level maximum by the level count changes the quantity rather than
     scaling it: *"this could be a useful feature itself but isn't a
     normalisation true to the original feature."*
  2. `missing_level_count` was then treated as the exception, on the grounds
     that it is scan-level on both sides. Also rejected: its denominator would
     be *"GT levels expected"*, which **is not derivable from the segmentation
     or image alone** — *"that's mixing supervision with features."* A scale
     built on supervision cannot be computed on real segmenter output, the one
     setting FACET exists for.
  3. Settled: intrinsic scalings (ratios, bounded-by-construction) proceed
     automatically; everything else requires human review; the default absent
     review is raw.
- **`rogue_island_count`'s scale is a threshold, not a ratio** (maintainer,
  2026-08-12) — the clean expectation is *none*, so a small declared count is
  defensible where a "full-blown failure" magnitude would not be. The exact
  value is **TBC**; this item ships the mechanism and sets nothing.
- **Neighbourhood-relative normalisation is the more meaningful direction for
  unbounded metrics** (maintainer, 2026-08-12) — comparing a vertebra's island
  count against its neighbours' rather than against a fixed constant. Logged to
  [`insights.md`](../insights.md) (2026-08-12) for triage at the next queue
  boundary; deliberately **not** built here, and not coupled to item 110's
  generalised neighbourhood API, which would make this item depend on a
  features/ refactor mid-stage. Item 110's API is named there as the natural
  mechanism when the feature-set selection vocabulary is next open.

To be updated during implementation.
