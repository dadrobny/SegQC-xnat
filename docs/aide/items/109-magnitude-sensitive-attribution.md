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

The fix is **not** a single universal scale, because the eight metrics do not
share units. They split in two:

- **Bounded metrics** — `unanchored_foreground_fraction` (baseline 0.0),
  `min_dominant_component_fraction` (baseline 1.0, decreasing),
  `mislabelled_volume_fraction` (0.0) and the other fraction-valued entries.
  These are mathematically confined to 0..1, so the full swing from baseline is
  derivable with no free parameter, and normalising by it is faithful.
- **Unbounded metrics** — `rogue_island_count`, `missing_level_count`. These
  have no natural full swing. Any denominator is either a hand-set judgement or
  a change of quantity: dividing `rogue_island_count` (defined as a **maximum
  over per-label entries**) by the number of levels converts a per-level
  worst-case into a scan-level density — a different and possibly useful
  feature, but not a normalisation of the original.

So: normalise where a genuine full swing exists, and report raw otherwise.

**In scope.** The normalisation and attribution logic, the optional per-metric
excursion field, and the affected rendering and tests.

**Not in scope.** New metrics; changing any metric's definition, baseline or
direction; `eval/per_mode.py`'s computation (item 112 owns the only authorised
change there); neighbourhood-relative normalisation (logged as backlog, see
Decisions).

## Acceptance Criteria

- [ ] **AC1: bounded metrics normalise by their derivable full swing.** For a
  metric confined to a known range, `normalised_delta` is `delta` divided by the
  distance from `baseline` to the far end of that range, and the divisor is
  derived from the metric's declaration, not hand-entered.
- [ ] **AC2: unbounded metrics are not normalised by default.**
  `normalised_delta is None` for a metric with no declared full swing, and the
  raw delta remains available on the same record.
- [ ] **AC3: an optional excursion may be declared.** `MetricSpec` gains an
  optional reference-excursion field, unset for every metric by default; when
  set, that metric normalises by it.
- [ ] **AC4: no excursion is set in this item.** Every shipped `MetricSpec`
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

- **Bounded-vs-unbounded is derivable from the existing declarations.** A
  metric named `*_fraction` with a `0.0` or `1.0` baseline is bounded 0..1; a
  metric named `*_count` is unbounded. If any metric resists that reading, the
  spec's classification is recorded explicitly per metric rather than inferred.
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

- **Normalise only where a real full swing exists** (maintainer, 2026-08-12).
  The originally-proposed case-intrinsic denominator for counts was rejected on
  the maintainer's observation that dividing a per-level maximum by the level
  count changes the quantity rather than normalising it: *"this could be a
  useful feature itself but isn't a normalisation true to the original
  feature."* Optional declared constants are permitted where someone can justify
  one; none is declared here.
- **Neighbourhood-relative normalisation is the more meaningful direction for
  unbounded metrics** (maintainer, 2026-08-12) — comparing a vertebra's island
  count against its neighbours' rather than against a fixed constant. Logged to
  [`insights.md`](../insights.md) (2026-08-12) for triage at the next queue
  boundary; deliberately **not** built here, and not coupled to item 110's
  generalised neighbourhood API, which would make this item depend on a
  features/ refactor mid-stage. Item 110's API is named there as the natural
  mechanism when the feature-set selection vocabulary is next open.

To be updated during implementation.
