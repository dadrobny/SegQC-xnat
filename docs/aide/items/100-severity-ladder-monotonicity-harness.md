# Item 100 — Severity-ladder monotonicity & cross-mode specificity harness

> **Created:** 2026-07-26 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 18 — Failure-Mode-Specific Metric Surface (G2, G7)
> **Queue:** [`../queue/queue-014.md`](../queue/queue-014.md) · Item 100
> *(third of five; item 098 named the stray-component population, item 099 built
> the eight per-mode metrics this item exercises, item 101 reports them
> cohort-wide, item 102 replays this harness as part of the stage validation)*
> **Objectives:** G2 (each §6 failure mode must have ≥1 named metric that moves
> monotonically with injected severity of *that* mode and is comparatively
> insensitive to the others — this item is the stage's G2 acceptance), G7 (the
> claim is *measured and regression-tested*, not asserted)
> **Suggested branch:** `aide/100-severity-ladder-monotonicity-cross-mode`

---

## Description

Item 099 proved *isolation on nine fixed corpus cases*: each of its eight
metrics attains its largest deviation from baseline on its own mode's single
case (`099`'s AC15, the 8 × 9 matrix). That is a **one-point** result. Stage
18's acceptance asks for something strictly stronger — that each metric **moves
monotonically with injected severity** — which needs a *graded* stimulus, and
that it is **comparatively insensitive to the others**, which needs the *other*
seven metrics measured over the same graded stimulus.

This item builds that harness: a new pure module,
`src/segfacet/eval/severity_ladder.py`, which

1. defines, for each of the eight §6 modes, a **severity ladder** — an ordered
   sequence of rungs, rung 0 being the untouched clean control and each later
   rung applying the mode's perturbation operator(s) at a strictly greater
   severity, built from the existing operators' constructor parameters
   (`perturbation.py:188-192`: *"operators are parameterised via their
   constructor"*);
2. runs **all eight** item-099 metrics at **every** rung of **every** ladder
   (the full ladder × metric response surface, not just the diagonal);
3. scores the surface: per ladder, is the designated metric monotone in its
   declared direction, does it strictly change at every rung, and how large is
   its response relative to every *foreign* metric's response on the same
   ladder;
4. **freezes the observed margins and the observed cross-mode couplings as
   module constants** so the bar is a ratchet: a future rule retune or feature
   change that flattens a metric, or that makes a metric more responsive to a
   foreign mode, fails a test instead of quietly eroding the stage's claim.

The harness is production code, not a test fixture — the same choice
`synth/regression.py` made (*"a small, importable verification library — **not**
a pytest module itself"*), for the same reason: item 102's stage validation and
any future drift check must call exactly the same logic the unit suite does.

### The eight ladders

Rung 0 is the clean base for every ladder: `build_clean_spine()` with its
defaults (L1–L5, labels 20–24, 1 mm isotropic, `curve_amplitude_mm=6.0`) —
byte-identical to the committed corpus's `_DEFAULT_BASE_PARAMS`
(`synth/corpus.py:88-92`), so item 099's measured baselines and per-case values
carry over unchanged. Every rung applies an ordered list of
`(operator_name, constructor_kwargs)` steps to a **fresh copy** of that base.

| §6 mode | Metric (item 099) | Operator | Severity knob | Kind | Rung severities |
|---|---|---|---|---|---|
| 1 | `unanchored_foreground_fraction` ↑ | `displace` | `displacement_mm` | continuous | 4, 8, 12, 16 mm |
| 2 | `min_dominant_component_fraction` ↓ | `fragment` | `n_pieces` | continuous | 2, 3, 4, 5 |
| 3 | `rogue_island_count` ↑ | `inject_islands` | `n_islands` | continuous | 1, 2, 3, 4 |
| 4 | `mislabelled_volume_fraction` ↑ | `relabel_swap` | **n affected labels** | affected-label-count | 1, 2 swaps |
| 5 | `missing_level_count` ↑ | `remove_level` | **n affected labels** | affected-label-count | 1, 2, 3 levels |
| 6 | `fov_clipped_label_count` ↑ | `crop_at_border` | **n affected labels** | affected-label-count | 1, 2, 3 labels |
| 7 | `out_of_order_label_count` ↑ | `sequence_break` | — | **degenerate (2-rung)** | 1 break |
| 8 | `overlapping_voxel_count` ↑ | `force_overlap` | `overlap_depth` | continuous | 1, 2, 3, 4 |

Concrete step lists (all targets explicit, so no operator ever consults
`seeded_rng` for a choice and the ladder is reproducible by construction):

- **1** — `displace(target_label=22, displacement_mm=s)`, one step per rung.
- **2** — `fragment(target_label=22, n_pieces=s)`, one step per rung.
- **3** — `inject_islands(target_label=22, n_islands=s, island_voxels=27)`.
- **4** — cumulative disjoint adjacent swaps:
  rung 1 `relabel_swap(20, 21)`; rung 2 adds `relabel_swap(22, 23)`.
- **5** — cumulative interior removals: `remove_level(21)`, then `(22)`, then
  `(23)`.
- **6** — cumulative crops: `crop_at_border(20, face="anterior", crop_depth=5)`,
  then label 21, then label 22.
- **7** — `sequence_break()` (default: relabel the tail L5 → 28/T13).
- **8** — `force_overlap(target_label=20, neighbour_label=21, overlap_depth=s)`.

Plus one **supplementary** ladder, outside the eight and outside the cross-mode
matrix: mode 2's *fused* half via cumulative `fuse(20, <next present>)` — see
Assumptions.

### Three modes have no continuous knob — how each is handled

Item 099 recorded, and this item confirms from the operator sources, that
`relabel_swap` (`identity_ordering_alignment.py:262-269`), `sequence_break`
(`:355-362`) and `remove_level` (`coverage_border_overlap.py:176`) take only
target-label selectors. Two of the three get a genuine ladder from the **count
of affected labels**; the third cannot, and says so:

- **Mode 4 (`relabel_swap`)** — *count ladder, 3 rungs.* Each disjoint adjacent
  swap mislabels two whole bodies, so `mislabelled_volume_fraction` steps
  0.0 → 0.4 → 0.8 on the five-level base. Three rungs, not four, because five
  labels admit only two disjoint adjacent pairs — recorded, not hidden.
- **Mode 5 (`remove_level`)** — *count ladder, 4 rungs.* Three interior levels
  (21, 22, 23) can be removed one at a time; `missing_level_count` steps
  0 → 1 → 2 → 3.
- **Mode 7 (`sequence_break`)** — *degenerate, 2 rungs, with the reason
  written down.* A count ladder is **structurally impossible** here, not merely
  inconvenient: `out_of_order_label_count` counts rank descents when the present
  labels are walked in ascending **integer** order, and under the default
  (TPTBox, item 093) convention `rank(v) == v - 1` for every value 1–24, so no
  relabel inside that block can produce a descent. Exactly one value in the
  whole vertebra range has a rank below its integer position — **28 = T13**
  (rank 19, between T12 and L1) — and because 28 exceeds every lumbar value it
  always sorts **last**, contributing at most **one** descent. A second break
  therefore cannot add a second out-of-order label. The metric is capped at 1.0
  on any single-anatomical-group synthetic base, so mode 7 carries an honest
  two-rung absent/present ladder, flagged `severity_kind == "degenerate"` and
  reported as such by the harness (AC12) — never silently presented as
  "monotone" alongside the seven graded ladders.

`crop_at_border` *does* have a continuous `crop_depth` knob, and the queue lists
it as such — but item 099's mode-6 metric is `fov_clipped_label_count`, a **count
of labels**, which is invariant to how deeply one label is clipped. Its severity
axis is therefore the number of clipped labels, with `crop_depth` pinned at the
corpus's 5. Recorded in Assumptions.

### The specificity bar

For metric `f` on ladder `L`, define the **span**

```
span_f(L) = max_r v_f(r) - min_r v_f(r)      (over all rungs, rung 0 included)
```

— the *range* the ladder drives the metric through, i.e. its response to a
**change** in that mode's severity. That, rather than deviation from baseline,
is what "insensitive to the others" means: a metric that jumps to a constant
offset on a foreign ladder and then ignores its severity is insensitive to that
mode. Then the dimensionless

```
response(m, f) = span_f(L_m) / span_f(L_f)        response(m, m) == 1.0
margin(m)      = 1.0 / max_{f != m} response(m, f)  (inf when the max is 0)
```

A ladder is **strictly specific** when `margin(m) > 1.0`: no foreign metric is
driven through more of its own full swing than the ladder's own metric is.
Pairs with `response(m, f) >= COUPLING_THRESHOLD` (0.25) are **recorded
couplings** — measured, named, caused, frozen — so a real cross-mode leak is
published rather than buried in a pass/fail bit.

**What this item is NOT:**

- **Not a change to the metrics.** `eval/per_mode.py` is untouched; the harness
  imports `compute_per_mode_metrics` and `PER_MODE_METRIC_SPECS` and computes no
  metric value of its own.
- **Not a change to the operators or the corpus.** `synth/**` is untouched; no
  new perturbation is registered; `tests/corpus/**` (fixtures, manifest, the
  nine goldens) is untouched. In particular this item does **not** add the
  missing `fuse` corpus case (`insights.md`, item 099) — it measures `fuse`
  in-memory instead.
- **Not a rule, threshold, schema or CLI change.** `heuristics/**`,
  `report_schema_v0.json`, `eval_report_schema_v0.json` and `cli.py` are
  untouched. Nothing here fires a finding.
- **Not the cohort report** (item 101) — nothing aggregates over a real cohort,
  reads a manifest, or writes a file.
- **Not a real-data claim.** Every ladder is synthetic. Stage 16/21 own real
  corpora; item 102 must not read this harness as closing a real-data row.

## Acceptance Criteria

- [ ] **AC1: the module and its public surface exist.**
  `segfacet.eval.severity_ladder` defines and exports, via `__all__`:
  `LadderRungSpec`, `LadderSpec`, `LadderPoint`, `LadderResult`,
  `HarnessResult`, `LadderVerdict`, `HarnessVerdict`, `CrossModeCoupling`,
  `SEVERITY_LADDERS`, `SUPPLEMENTARY_LADDERS`, `DEGENERATE_LADDER_MODES`,
  `KNOWN_CROSS_MODE_COUPLINGS`, `RECORDED_MARGINS`, `COUPLING_THRESHOLD`,
  `LADDER_SEED`, `evaluate_ladder`, `run_severity_harness`, `score_harness`.
  Every one of those names is also importable from `segfacet.eval` (added to
  `eval/__init__.py`'s import block and `__all__`). All eight dataclasses are
  `@dataclass(frozen=True)`.

- [ ] **AC2: the ladder registry covers exactly the eight §6 modes.**
  `SEVERITY_LADDERS` is an immutable mapping whose key set is exactly
  `{1,2,3,4,5,6,7,8}` (`CLEAN_CONTROL_MODE` is not a key); for every key `k`,
  `SEVERITY_LADDERS[k].failure_mode == k` and `.failure_mode_name ==
  segfacet.synth.perturbation.FAILURE_MODE_NAMES[k]` character-for-character.

- [ ] **AC3: the ladders use registered operators only.** Every
  `LadderRungSpec.steps` entry names an operator present in
  `segfacet.synth.perturbation.perturbation_names()`, and every step's kwargs
  are accepted by that operator's constructor (constructing each declared
  operator raises nothing). No new perturbation is registered by this item.

- [ ] **AC4: the metric assignment is item 099's, not a new one.** For every
  mode `k`, the harness scores ladder `k` against
  `PER_MODE_METRIC_SPECS[k].metric_name`, and `severity_ladder.py` contains no
  metric arithmetic of its own: its only route to a metric value is a call to
  `segfacet.eval.per_mode.compute_per_mode_metrics`, asserted by reading the
  module source (the drift guard, mirroring item 099's AC18).

- [ ] **AC5: rung 0 is the clean control, at baseline on all eight metrics.**
  Every ladder's rung 0 has `steps == ()` and `severity == 0.0`, and its
  `PerModeMetrics` has, for each of the eight entries, `value` exactly equal to
  that mode's `MetricSpec.baseline` (`1.0` for mode 2, `0.0` for the other
  seven), with no entry `None`.

- [ ] **AC6: no metric is ever `None` anywhere in the harness.** Across every
  ladder and every rung, all eight `PerModeMetric.value` fields are `float`
  (never `None`) — the harness always supplies a record *and* a candidate/GT
  pair *and*, for the mode-8 ladder, a populated `overlaps` block.

- [ ] **AC7: rung severities are strictly increasing.** For every ladder,
  `rungs[0].severity == 0.0` and `rungs[i].severity < rungs[i+1].severity` for
  every `i`.

- [ ] **AC8: every ladder has ≥3 rungs except the declared degenerate one.**
  `len(spec.rungs) >= 3` for every mode not in `DEGENERATE_LADDER_MODES`;
  each mode **in** `DEGENERATE_LADDER_MODES` has exactly 2 rungs.

- [ ] **AC9: the designated metric is monotone in its declared direction.** For
  every one of the eight ladders, the sequence of the designated metric's values
  across rungs is non-decreasing when `PER_MODE_METRIC_SPECS[k].direction ==
  "increases"` and non-increasing when it is `"decreases"`.

- [ ] **AC10: the designated metric changes strictly at every rung
  transition.** For every ladder and every adjacent rung pair,
  `abs(v(r+1) - v(r)) > 1e-9` — a ladder that plateaus (the failure mode a
  purely-directional monotonicity check would pass) fails this.

- [ ] **AC11: the severity axis is declared honestly per ladder.**
  `severity_kind` is `"continuous"` for modes 1, 2, 3, 8 with
  `severity_parameter` equal to the operator's actual constructor keyword
  (`"displacement_mm"`, `"n_pieces"`, `"n_islands"`, `"overlap_depth"`
  respectively); `"affected-label-count"` for modes 4, 5, 6 with
  `severity_parameter == "n_affected_labels"`; `"degenerate"` for every mode in
  `DEGENERATE_LADDER_MODES`. Those three values are the only ones permitted.

- [ ] **AC12: the degenerate ladder is declared, never silent.**
  `DEGENERATE_LADDER_MODES == frozenset({7})`; `SEVERITY_LADDERS[7].rationale`
  is a non-empty string naming the transitional-label cap (it contains the
  substring `"28"`); a ladder has `severity_kind == "degenerate"` **iff** its
  mode is in `DEGENERATE_LADDER_MODES`; a ladder has exactly 2 rungs **iff** its
  mode is in `DEGENERATE_LADDER_MODES`; and `HarnessResult.to_dict()` carries
  `"degenerate": true` for mode 7 and `false` for the other seven.

- [ ] **AC13: `score_harness` computes the response surface as specified.** For
  the identity assignment, `HarnessVerdict` exposes, per ladder `m`, a
  `responses` mapping over all eight metrics with `responses[m] == 1.0` and,
  for each `f != m`, `responses[f] == pytest.approx(span_f(L_m) /
  span_f(L_f))` recomputed independently in the test from the harness's stored
  per-rung values.

- [ ] **AC14: uncoupled ladders are strictly specific.** For every ladder `m`
  with no entry in `KNOWN_CROSS_MODE_COUPLINGS`, `response(m, f) < 1.0` for
  every `f != m` and `margin(m) > 1.0`; its `LadderVerdict.status` is
  `"strict"`.

- [ ] **AC15: the coupling table exactly matches what is measured — no hidden
  leak, no stale entry.** The set of `(ladder_mode, foreign_mode)` pairs with
  measured `response >= COUPLING_THRESHOLD` equals the set of pairs in
  `KNOWN_CROSS_MODE_COUPLINGS`; every entry's `cause` is a non-empty string; and
  no entry has `foreign_mode == ladder_mode`.

- [ ] **AC16: the coupling table is a ratchet.** For every entry,
  `measured_response <= entry.recorded_response * 1.05`; and for every mode,
  `measured margin >= RECORDED_MARGINS[mode] * 0.95` (with `math.inf` compared
  as such). `RECORDED_MARGINS` has all eight modes as keys.

- [ ] **AC17: a coupled ladder is reported as coupled, not as a pass.** Every
  ladder carrying a `KNOWN_CROSS_MODE_COUPLINGS` entry has
  `LadderVerdict.status == "coupled"`, a non-empty `coupled_modes` tuple, and
  appears with that status in `HarnessVerdict.to_dict()`; `HarnessVerdict.passed`
  is `True` for the identity assignment (couplings are recorded facts, not
  failures) while `HarnessVerdict.summary()` names every coupled ladder.

- [ ] **AC18: the negative control fails.** `score_harness(harness,
  assignment={**identity, 2: 3, 3: 2})` — mode 2's ladder scored against mode
  3's metric and vice versa — returns a verdict with `passed is False`, whose
  failing ladders include 2 and 3 with a non-empty `failures` tuple, while
  `score_harness(harness)` on the same `HarnessResult` returns `passed is True`.
  This proves the harness can actually fail.

- [ ] **AC19: the mode-8 ladder reproduces the committed corpus's overlap
  count.** The mode-8 rung with `overlap_depth == 3` (target 20, neighbour 21,
  default base — the committed `mode8_force_overlap` recipe) yields
  `overlapping_voxel_count == 1950.0`, the value item 099's AC14 pins against
  the corpus, confirming the harness's in-memory `overlap_mask_stack`
  reconstruction is the same technique `synth/regression.py:167-184` uses.

- [ ] **AC20: `overlapping_voxel_count` is 0.0 on every non-mode-8 ladder.** At
  every rung of the seven other ladders (and the supplementary one), mode 8's
  value is exactly `0.0` — the reconstruction is applied only where the ladder
  declares it, and a single-integer label map cannot otherwise encode an
  overlap.

- [ ] **AC21: the supplementary `fuse` ladder closes mode 2's fused half.**
  `SUPPLEMENTARY_LADDERS` is a tuple containing exactly one `LadderSpec` with
  `operator`-step name `"fuse"` and `failure_mode == 2`; it has ≥3 rungs; its
  `min_dominant_component_fraction` strictly decreases at every rung transition;
  and its mode is **not** a key of `SEVERITY_LADDERS`' cross-mode scoring —
  `score_harness` ignores `HarnessResult.supplementary` entirely.

- [ ] **AC22: the harness is deterministic.** Two `run_severity_harness()` calls
  in the same session produce `to_dict()` outputs that compare equal, and the
  perturbed label-map arrays at each rung are element-wise equal between the two
  runs (`np.array_equal`).

- [ ] **AC23: the harness is pure.** `run_severity_harness()` opens no file,
  reads no clock, never mutates the clean base image or array it derives every
  rung from (a `np.array_equal` check against a pre-run copy), and leaves
  `tests/corpus/**` byte-unchanged.

- [ ] **AC24: results round-trip through JSON unchanged.**
  `HarnessResult.to_dict()` and `HarnessVerdict.to_dict()` return plain-JSON
  structures (dict / list / str / float / int / bool / None only — no tuples, no
  dataclasses, no numpy scalars, no non-string mapping keys) for which
  `json.loads(json.dumps(d)) == d`.

- [ ] **AC25: an operator failure propagates, never truncates the ladder.**
  `evaluate_ladder` on a hand-built `LadderSpec` whose step is out of range
  (e.g. `displace(target_label=22, displacement_mm=60.0)`, which cannot fit the
  FOV) raises `segfacet.io.FacetInputError` rather than returning a shorter
  ladder or a rung with `None` values.

- [ ] **AC26: the scope fence holds.** `src/segfacet/eval/per_mode.py`,
  `src/segfacet/eval/metrics.py`, `src/segfacet/synth/**`,
  `src/segfacet/heuristics/**`, `src/segfacet/features/**`,
  `src/segfacet/cli.py`, `src/segfacet/report_schema_v0.json`,
  `src/segfacet/eval/eval_report_schema_v0.json` and `tests/corpus/**` are all
  byte-identical to their pre-100 state; the only production files this item
  adds or edits are `src/segfacet/eval/severity_ladder.py` (new) and
  `src/segfacet/eval/__init__.py` (re-export block + docstring sentence).

## Assumptions

Clarify mode is `assume` (`aide.toml`'s `loop.clarify`). Each default below was
chosen against the operator sources and item 099's measured values; the
reasoning is recorded so the validator can audit it at the queue boundary.

- **The harness is production code under `eval/`, not a test module.** The queue
  says "build the harness"; item 102 must *run* it and record its margins. The
  repo's precedent for exactly this shape is `synth/regression.py` ("a small,
  importable verification library — **not** a pytest module itself — so the
  parametrised suite and any future drift/meta-tests call exactly the same
  comparison logic"). Placed in `eval/` beside the metrics it exercises;
  `eval/per_mode.py` already imports from `segfacet.synth`, so the dependency
  direction is established.

- **The base is `build_clean_spine()`'s default L1–L5, identical to the
  corpus.** A six-level L1–L6 span *is* canonically contiguous and would buy one
  extra rung on the mode-4 and mode-5 count ladders. Rejected: it changes the
  lateral-arc geometry (the hump is a sine over `n` bodies), which would break
  the AC19 cross-check against the committed corpus's `1950.0`, and would divorce
  every measured number from item 099's published values for no gain the queue
  asked for. The mode-4 ladder is 3 rungs as a direct consequence, which meets
  the queue's "at least three rungs" bar and is recorded rather than papered over.

- **Mode 6's severity axis is the number of clipped labels, not `crop_depth`.**
  The queue lists `crop_at_border(crop_depth=…)` among the five continuous
  knobs. But item 099's mode-6 metric is `fov_clipped_label_count` — a **count
  of labels with an unexpected FOV-face touch** — which is invariant to clip
  depth: one label clipped 1 voxel deep and one clipped 15 voxels deep both read
  `1.0`. A `crop_depth` ladder would therefore be perfectly flat and fail AC10.
  `crop_depth` is pinned at the corpus's `5` and the ladder sweeps the number of
  cropped labels (20, then 20+21, then 20+21+22). This is a correction to the
  queue's assumption, made explicit rather than silently followed.

- **Mode 7's ladder is degenerate for a structural reason, stated in the module
  and in `rationale`.** See the Description. The alternative — fabricating a
  custom `LabelConvention` with several out-of-place values to manufacture extra
  rungs — is rejected: it would measure the *convention*, not the segmentation,
  and would make the one metric whose ladder is honest look graded.

- **`fuse` gets a supplementary mode-2 ladder rather than a corpus case.** Item
  099's `insights.md` entry (2026-07-26) records that `fuse` has **no corpus
  case**, so "a mode-2 severity ladder built only from `fragment(n_pieces=…)`
  measures under-segmentation while claiming to cover the mode". Adding the
  tenth recipe entry is the real fix, but it regenerates the manifest and all
  nine goldens — squarely item 098's kind of work and out of scope here (AC26).
  The in-scope half is measurable in memory: cumulative `fuse` steps drive
  `min_dominant_component_fraction` down exactly as `fragment` does (each fusion
  adds one more disconnected body to the surviving label), so the metric's claim
  to cover **both** halves of §6 mode 2 becomes tested rather than asserted. It
  is kept *outside* the eight-ladder cross-mode matrix so the matrix stays a
  square 8 × 8 with one ladder per mode. The insight stays open for the corpus
  fix.

- **"Comparatively insensitive" is measured as span *range*, not deviation from
  baseline.** A metric that jumps to a fixed offset on a foreign ladder and then
  ignores that ladder's severity **is** insensitive to that mode in the sense
  Stage 18 means; deviation-from-baseline would score it as maximally coupled.
  Concretely this matters for `unanchored_foreground_fraction` on the mode-8
  ladder: `force_overlap` shifts the target by `gap + overlap_depth` voxels, so
  most of the unanchored signal comes from the constant 15 mm inter-body gap and
  barely responds to `overlap_depth`. Item 099 measured the baseline-deviation
  form of this collision (0.123 on `mode8_force_overlap`); the range form is the
  honest reading on a ladder.

- **One cross-mode coupling is anticipated: the mode-6 ladder driving
  `unanchored_foreground_fraction` (metric 1).** Item 099 recorded the per-case
  version (0.120 on `mode6_crop_at_border` vs 0.146 on mode 1's own case) with
  the cause: `displace`, `crop_at_border` and `force_overlap` all translate a
  body rigidly, so all three put candidate foreground over GT background. On a
  ladder this is expected to *exceed* the strict bar, because mode 1's own
  ladder is capped by the FOV (the body must stay ≥1 voxel inside every face,
  limiting `displacement_mm` to ≈19.8 mm on this base) while the mode-6 ladder
  scales the same signal linearly with the number of cropped labels. That is a
  real finding about metric 1's specificity, not a harness defect: modes 6 and 8
  have clean isolators of their own, so the coupling is one-directional and
  harmless *for attribution*, but it belongs in the record for Stage 20's
  specificity work. The table is therefore built to hold and publish it (AC15,
  AC17) rather than to be tuned until it is empty. The anticipated entries are
  a hypothesis inherited from item 099, to be replaced by measurement; whatever
  the builder measures goes in the table with its cause, and any coupling
  outside `{(6, 1)}` is called out in the Decisions log.

- **`RECORDED_MARGINS` / `KNOWN_CROSS_MODE_COUPLINGS` live in the production
  module, filled in by measurement.** The test-writer cannot know these numbers
  without running code, and item 099's precedent (`_EXPECTED_ISOLATION_MATRIX`
  in the test module) does not transfer: there the values were derivable from the
  committed goldens. Freezing them in the module keeps the ratchet available to
  item 102 and to any future caller, and the tautology risk (a builder writing
  numbers that trivially match) is closed by pairing every table-agreement AC
  with an independent bar the numbers must *also* satisfy — AC14's `margin > 1.0`
  for uncoupled ladders, AC15's exact-match-with-measurement in both directions,
  and AC10's strict-change requirement.

- **Every ladder step passes explicit target labels.** All the operators fall
  back to `_choose_label`/`_choose_adjacent_pair` (i.e. `seeded_rng`) only when a
  target is `None`. Pinning every target makes the ladders reproducible without
  relying on RNG stability, and keeps rung *k*'s perturbation a strict superset
  of rung *k−1*'s for the cumulative count ladders. `LADDER_SEED = 0` is still
  passed to `apply` to honour the `Perturbation` signature and to match the
  corpus recipe's seed.

- **Modes 1, 4 and 5 read the candidate/GT route; mode 8 needs the
  reconstructed `overlaps` block.** Both facts are item 099's, inherited
  verbatim: the pipeline record is structurally blind to displacement and to
  relabel-swap (the interpolating spline refits through the moved centroids),
  and a single-integer label map cannot encode an overlap. So each rung supplies
  `record=extract_feature_record(perturbed, bundled_default_config())`,
  `candidate=<perturbed array>`, `gt=<clean base array>`, and — for the mode-8
  ladder only — a record whose `overlaps` key is rebuilt by the same
  `np.stack([perturbed == target, clean == neighbour])` →
  `detect_overlaps` → `overlap_to_dict` technique
  `synth/regression.py:167-184` uses. That six-line technique is reimplemented
  locally (the existing one takes a manifest case dict and returns *findings*,
  not a record) and pinned to the corpus by AC19 rather than by a refactor of
  `regression.py`, which is out of scope.

- **`island_size_ratio` stays at item 099's default `0.10`.** Sweeping it is
  a metric-calibration question, not a severity-ladder question; the mode-3
  ladder sweeps `n_islands` at the default 27-voxel island size, comfortably
  below `0.10 × 18750`.

## Implementation Steps

All production changes are under `source_dir = src/segfacet`.

1. **Create `src/segfacet/eval/severity_ladder.py`** with a module docstring in
   the package's house style: what it is (Stage 18's G2 acceptance harness), how
   it differs from item 099 (graded ladder vs. single case), the ladder table,
   the span/response/margin definitions, the degenerate-ladder policy, the
   purity contract, a **Scope fence** naming what it is not, and a `Public API`
   block listing the exported names.

2. **Declarative ladder types.**
   - `LadderRungSpec` — `index: int`, `severity: float`, `label: str`,
     `steps: Tuple[Tuple[str, Mapping[str, Any]], ...]` (operator registry name
     + constructor kwargs, applied in order to a fresh copy of the base; rung 0
     has `steps == ()`).
   - `LadderSpec` — `failure_mode: int`, `failure_mode_name: str`,
     `operator: str`, `severity_parameter: str`, `severity_kind: str`,
     `rungs: Tuple[LadderRungSpec, ...]`, `rationale: str`,
     `overlap_reconstruction: Optional[Tuple[int, int]]` (`(target, neighbour)`;
     set only on the mode-8 ladder).
   Build `SEVERITY_LADDERS: Mapping[int, LadderSpec]` as a
   `types.MappingProxyType` from a module-level declarative table, reading
   `failure_mode_name` from `FAILURE_MODE_NAMES` so names cannot drift (AC2),
   and `SUPPLEMENTARY_LADDERS: Tuple[LadderSpec, ...]` holding the `fuse` ladder.

3. **Case construction** — a private `_apply_steps(base_img, steps)` that, for
   each step, looks the class up with `get_perturbation(name)`, constructs it
   with the declared kwargs, and calls `apply(current_img, LADDER_SEED)`,
   threading the output image into the next step. Never mutates `base_img`
   (every operator already copies, but assert the contract by never writing
   into the base array).

4. **Per-rung measurement** — a private `_measure(base, spec, rung)` returning a
   `LadderPoint(rung, severity, label, metrics)` where `metrics` is
   `compute_per_mode_metrics(record, candidate=perturbed_arr, gt=base_arr,
   spacing=base.spacing)`; `record` is
   `extract_feature_record(perturbed_img, config)` with
   `config = bundled_default_config()` by default, plus — when
   `spec.overlap_reconstruction` is set — its `overlaps` key replaced by the
   mask-stack reconstruction (Assumptions). Compute the **rung-0 point once**
   per harness run and share it across all nine ladders: rung 0 is the same
   clean base for every ladder, and its reconstructed overlaps block is empty
   anyway.

5. **`evaluate_ladder(spec, *, base=None, config=None) -> LadderResult`** —
   builds every rung's `LadderPoint` in order and returns
   `LadderResult(spec=spec, points=(...))`. Deliberately carries **raw data
   only**: no spans, no responses, no verdict, so that scoring is a pure
   function of a `LadderResult` and the negative control (AC18) needs no
   recomputation.

6. **`run_severity_harness(*, base=None, config=None) -> HarnessResult`** —
   evaluates the eight ladders plus the supplementary one and returns
   `HarnessResult(ladders=..., supplementary=..., base_params=...)` with
   `to_dict()` (`_tuples_to_lists(dataclasses.asdict(self))`, copying
   `per_mode.py`'s local helper rather than importing `eval.metrics`) and a
   `by_mode(k)` keyed accessor.

7. **`score_harness(harness, *, assignment=None) -> HarnessVerdict`** — the pure
   scorer. `assignment: Mapping[int, int]` maps ladder mode → metric mode,
   defaulting to the identity read from `PER_MODE_METRIC_SPECS`' keys. Computes
   `span`, `response`, `margin`, `monotone`, `strictly_changed`, `status`
   (`"strict"` / `"coupled"`), `coupled_modes`, and a `failures: Tuple[str, ...]`
   of human-readable reasons per ladder into `LadderVerdict`; folds them into
   `HarnessVerdict(passed, per_ladder, ...)` with `to_dict()` and a
   `summary() -> str` naming every degenerate and every coupled ladder. `passed`
   is `False` iff any ladder is non-monotone, plateaus, or violates its recorded
   coupling/margin ratchet — a *recorded* coupling is a fact, not a failure
   (AC17). Guard `span_f(L_f) == 0.0` (impossible for the identity assignment
   given AC10, reachable under a mis-assignment) by scoring that response as
   `math.inf` and recording an explicit failure string, never by dividing by
   zero.

8. **Frozen constants** — `COUPLING_THRESHOLD = 0.25`,
   `DEGENERATE_LADDER_MODES = frozenset({7})`, `LADDER_SEED = 0`,
   `CrossModeCoupling(ladder_mode, foreign_mode, recorded_response, cause)`,
   `KNOWN_CROSS_MODE_COUPLINGS: Tuple[CrossModeCoupling, ...]` and
   `RECORDED_MARGINS: Mapping[int, float]`. **Fill these by running the harness
   once and transcribing the measured values**, rounding each recorded response
   *up* and each recorded margin *down* to 4 significant figures so the ratchet
   has no float-equality knife edge, and writing a one-line `cause` for every
   coupling that names the operator artefact responsible.

9. **`src/segfacet/eval/__init__.py`** — add a
   `from .severity_ladder import (...)` block (alphabetically after `.report`),
   append the names to `__all__`, and extend the package docstring's running
   sentence with the severity-ladder harness and its item number (100), naming
   it as the graded-stimulus counterpart to item 099's per-case surface.

10. **Do NOT touch** `eval/per_mode.py`, `eval/metrics.py`, `eval/report.py`,
    `eval/harness.py`, `heuristics/**`, `features/**`, `synth/**`, `cli.py`,
    either JSON schema, or `tests/corpus/**` (AC26).

## Testing Strategy

- **Framework:** `pytest`. One new module,
  `tests/test_100_severity_ladder.py`. No existing test module is modified.

- **Cost control — the load-bearing fixture decision.** The harness builds ~33
  perturbed cases and runs `extract_feature_record` (Stage 2 + Stage 3) on each,
  over a ~780 k-voxel volume. The test module must build the harness **once**,
  in a `@pytest.fixture(scope="module")`, and every AC must assert against that
  one `HarnessResult`; only AC22 (determinism), AC23 (purity) and AC25
  (error propagation) may trigger additional runs, and AC22's second run is the
  only full one. Scoring (AC13-AC18) is pure and re-runs freely off the cached
  result.

- **AC1-AC4, AC7, AC8, AC11, AC12 (declarative surface)** — introspection tests:
  `__all__` contents and `segfacet.eval` re-export; `dataclasses.fields`;
  `frozen=True` via an attempted assignment raising `FrozenInstanceError`;
  `SEVERITY_LADDERS` key set and name agreement with `FAILURE_MODE_NAMES`; every
  step's operator in `perturbation_names()` and constructible with its declared
  kwargs; strictly increasing severities; rung counts; the
  `severity_kind`/`severity_parameter` vocabulary; and the iff-pairs in AC12
  (degenerate ⟺ mode 7 ⟺ 2 rungs). AC4's drift guard reads
  `Path(segfacet.eval.severity_ladder.__file__).read_text()` and asserts the
  presence of a `compute_per_mode_metrics(` call and the absence of any
  re-derivation of a metric (no `np.count_nonzero`, no `out_of_order_labels`,
  no `stray_component_sizes` in the module source).

- **AC5, AC6, AC9, AC10, AC19, AC20 (the measured surface)** — parametrised over
  the eight modes off the module-scoped harness. AC9/AC10 read `direction` from
  `PER_MODE_METRIC_SPECS` rather than a second hard-coded copy. AC10 asserts on
  the *sequence of adjacent differences*, so the failure message names the rung
  pair that plateaued. AC19 pins the single `1950.0` literal, cross-referenced in
  a comment to item 099's AC14.

- **AC13-AC18 (the scoring layer — the load-bearing tests)** — the test
  **recomputes** spans and responses independently from
  `HarnessResult`'s stored per-rung values (a five-line loop, not a call back
  into `score_harness`) and asserts agreement, so the scorer is checked against
  arithmetic rather than against itself. Then: AC14's strict bar on uncoupled
  ladders; AC15's two-way set equality between measured couplings and the frozen
  table (the direction that catches a *hidden* leak and the direction that
  catches a *stale* entry); AC16's ratchet inequalities; AC17's status/summary
  reporting. AC18 is the negative control — build the swapped assignment, assert
  `passed is False` **and** that ladders 2 and 3 are the ones named, then assert
  the identity assignment on the same object still passes, proving the failure
  came from the assignment and not from a broken harness.

- **AC21 (the `fuse` ladder)** — its own focused test: exactly one
  supplementary spec, operator `"fuse"`, mode 2, ≥3 rungs, strictly decreasing
  `min_dominant_component_fraction`, and `score_harness` output unchanged when
  `HarnessResult.supplementary` is emptied (proving it is outside the matrix).

- **AC22-AC24 (determinism, purity, JSON)** — two harness runs compared via
  `to_dict()` equality and `np.array_equal` on the per-rung arrays; a
  `copy.deepcopy`/`np.array_equal` snapshot of the base image and array taken
  before the run and compared after; `monkeypatch`-based assertions that no
  `open`/`Path.write_bytes` is called and no `time`/`datetime` is read;
  `json.loads(json.dumps(d)) == d` plus a recursive type walk asserting only
  JSON-native types and `str` mapping keys.

- **Adversarial / edge cases:**
  - **AC25** — a hand-built `LadderSpec` with `displacement_mm=60.0` raises
    `FacetInputError` out of `evaluate_ladder`; likewise a step naming an
    unregistered operator raises `KeyError` from `get_perturbation` rather than
    being skipped.
  - A `LadderSpec` with a single rung (rung 0 only) — `evaluate_ladder` returns
    a one-point result and `score_harness` records an explicit failure string
    rather than dividing by a zero span.
  - An assignment mapping a ladder to a mode outside `1..8` → `KeyError`/
    `FacetInputError`, not a silent skip.
  - `score_harness` on a `HarnessResult` whose ladders tuple is empty → an empty
    verdict with `passed is True` and an empty `per_ladder`, not an exception
    (so item 101/102 can call it defensively).
  - Baseline sanity: rung 0's record run through `run_qc` with the bundled
    default config still verdicts `pass` with zero findings — the positive
    control item 036 guarantees, re-asserted here because every ladder's
    normalisation depends on it.
  - A non-default `config` argument threads through to
    `extract_feature_record` (call with `bundled_default_config()` explicitly
    and compare to the default-argument result).

- **Existing tests to reconcile** (grep sweep for assumptions this item could
  invalidate — **all are expected to stay green unmodified**; an edit to any of
  them is a red flag for the validator, because this item adds one module and
  changes no existing behaviour):
  - `tests/test_099_per_mode_metrics.py` — pins the eight metrics, their
    directions, baselines and the frozen 8 × 9 isolation matrix. This item is a
    pure consumer; if any assertion there would have to move, the harness is
    wrong, not the metric.
  - `tests/test_036_perturbation_framework.py`,
    `tests/test_037_component_shape_perturbations.py`,
    `tests/test_038_coverage_border_overlap_perturbations.py`,
    `tests/test_039_identity_ordering_alignment_perturbations.py` — these assert
    on the perturbation **registry** (`perturbation_names`, `iter_perturbations`,
    `_PERTURBATIONS`). This item registers no new operator and changes no
    operator, so every registry-membership assertion must be untouched.
  - `tests/test_036_clean_gt.py` — pins `build_clean_spine`'s default span,
    shape and clean-pass property, which rung 0 relies on.
  - `tests/test_040_synthetic_corpus.py`, `tests/test_041_regression_suite.py`,
    `tests/test_042_golden_determinism.py` — the corpus, manifest and nine
    goldens. AC26 forbids touching `tests/corpus/**`; AC19 only *reads* the
    corpus's known 1950.0 value as a literal, and adds no fixture.
  - `tests/test_054_metrics.py`, `tests/test_050_overlap.py` — `eval/metrics.py`
    and `eval/overlap.py` are untouched.
  - Grep `tests/` for any exhaustive `segfacet.eval.__all__ ==` assertion before
    assuming AC1's growth is free — the sweep run while writing this spec found
    only membership checks (`assert name in eval_pkg.__all__`,
    `test_099_per_mode_metrics.py:267`), which AC1 does not break, but re-check
    at implementation time.

## Validation

Beyond the unit suite, the point of this item is a **table a human reads** — the
Stage-18 G2 claim in one page. From the repo root with the venv bootstrapped:

```
.venv/bin/python -c "from segfacet.eval import run_severity_harness, score_harness; h = run_severity_harness(); print(score_harness(h).summary())"
```

Confirm by inspection that:

1. All eight modes appear, each with its operator, severity knob, rung
   severities and the designated metric's value at every rung — and that the
   designated metric's column moves in one direction only, changing at every
   step (mode 2 downward, the other seven upward).
2. **Mode 7 is explicitly marked degenerate (2 rungs)** with its reason, and no
   other mode is. This is the "not both silent" check: the report must never let
   a two-rung ladder read as a graded one.
3. Modes 4, 5 and 6 are marked `affected-label-count`, so a reader can see at a
   glance which ladders are counts of affected labels rather than a physical
   magnitude.
4. The per-ladder margins are printed, and every coupled ladder names the
   foreign metric it drives and the cause. Sanity-check the anticipated one: the
   mode-6 (crop) ladder driving `unanchored_foreground_fraction`.
5. The supplementary `fuse` ladder appears, showing
   `min_dominant_component_fraction` falling as bodies are absorbed — the fused
   half of §6 mode 2, measured for the first time.

Then run the negative control by hand and confirm it fails loudly:

```
.venv/bin/python -c "from segfacet.eval import run_severity_harness, score_harness; h = run_severity_harness(); v = score_harness(h, assignment={1:1,2:3,3:2,4:4,5:5,6:6,7:7,8:8}); print(v.passed); print(v.summary())"
```

It must print `False` and name ladders 2 and 3.

No `[validation]` profile is required: this runs on the plain CPU venv with no
optional dependency. If the venv is not bootstrapped, run
`python .aide/scripts/aide.py env --bootstrap` first rather than recording the
step as unverified.

## Dependencies

- **Item 036** (`Perturbation` / `Expectation` / `PerturbationResult`, the
  registry, `seeded_rng`, and `build_clean_spine` — the rung-0 base and the
  operator contract every step is applied through) — ✅.
- **Item 037** (`fragment`, `fuse`, `inject_islands` and their `n_pieces` /
  `n_islands` constructor knobs) — ✅.
- **Item 038** (`remove_level`, `crop_at_border`, `force_overlap` and their
  `crop_depth` / `overlap_depth` knobs) — ✅.
- **Item 039** (`displace`, `relabel_swap`, `sequence_break` and the
  `displacement_mm` knob) — ✅.
- **Item 040** (the committed corpus's `_DEFAULT_BASE_PARAMS` and the
  `mode8_force_overlap` recipe parameters AC19 pins against) — ✅.
- **Item 041** (`synth/regression.py`'s `overlap_mask_stack` reconstruction
  technique the mode-8 ladder reimplements, and the importable-verification-
  library precedent this module follows) — ✅.
- **Item 093** (the TPTBox default convention whose rank table is what caps
  mode 7's ladder at one out-of-order label) — ✅.
- **Item 098** (`stray_component_sizes` / `stray_component_count`, read
  indirectly through mode 3's metric) — ✅.
- **Item 099** (`eval/per_mode.py` — `compute_per_mode_metrics`,
  `PER_MODE_METRIC_SPECS`, `PerModeMetrics`, the eight metric names, directions
  and baselines; and the recorded cross-mode collision hypotheses this item
  measures on ladders) — ✅.

**Downstream:** item 101 may cite this harness's margins in the cohort report's
provenance; item 102 replays the harness end-to-end, records the observed
margins in `progress.md`, and must name mode 7's degenerate ladder explicitly
when ticking Stage 18's G2 acceptance. Neither blocks this item.

## Decisions & Trade-offs

Implemented `src/segfacet/eval/severity_ladder.py` and re-exported its public
surface from `eval/__init__.py`, exactly as specced. Notes on choices made
during implementation, and the actual measured numbers:

- **Mode 4/5/6 severity values are literal `n_affected_labels` counts, not
  `n swaps`/`n crops`.** The queue table's "Rung severities: 1, 2 swaps" etc.
  is a shorthand for the *operation* count; AC11 pins the field name
  `severity_parameter == "n_affected_labels"`. Since one `relabel_swap`
  affects **two** labels at once, mode 4's rungs carry `severity = 2.0, 4.0`
  (not `1.0, 2.0`) so the stored `severity` value literally equals the count
  of affected labels, matching the field's own name. Modes 5 and 6 remove/
  crop one label per cumulative step, so their `severity` values (`1.0, 2.0,
  3.0`) already coincide with both readings.

- **`_measure` always passes `candidate`/`gt` (the perturbed array vs. the
  clean base array) to `compute_per_mode_metrics`, for every ladder** —
  simpler than routing per-mode as item 099's Assumptions describe (modes
  1/4/5 need the pair, others don't), and harmless: the metrics that don't
  use `candidate`/`gt` (2, 3, 6, 7, 8) simply ignore the extra kwargs. This
  keeps `_measure` a single, uniform function instead of a per-mode dispatch,
  with no observable difference in results.

- **Rung 0 is computed once and shared across all nine ladders** (the eight
  primary plus the supplementary `fuse` ladder), per the Implementation
  Steps' explicit instruction — `run_severity_harness` builds it once via a
  private helper and reuses the same `LadderPoint` object for every ladder's
  `points[0]`. `evaluate_ladder` (the standalone, per-ladder entry point used
  directly by AC23/AC25's adversarial tests) does **not** share rung 0 across
  calls — it always computes its own, keeping that function's contract
  simple and independent of the harness's internal caching.

- **A second cross-mode coupling was measured beyond the one item 099
  anticipated.** The Assumptions log named only `{(6, 1)}` as anticipated,
  while noting "whatever the builder measures goes in the table ... any
  coupling outside `{(6, 1)}` is called out here." The actual measured
  8x8 response surface (via `run_severity_harness()` + a script recomputing
  `span`/`response`/`margin` independently) found **two** entries with
  `response >= COUPLING_THRESHOLD (0.25)`:
  - `(ladder_mode=6, foreign_mode=1)`: response **2.789** (rounded up to
    4 sig figs: `2.79`) — matches the anticipated direction and even exceeds
    the strict bar, exactly as item 099 predicted (`crop_at_border` rigidly
    translates a body like `displace`/`force_overlap`, and mode 1's own
    ladder is FOV-capped at ~19.8mm `displacement_mm` on this base while
    mode 6 scales linearly with the number of cropped labels).
  - `(ladder_mode=8, foreign_mode=1)`: response **0.9629** (rounded up:
    `0.9629`), **not** anticipated by item 099. Cause: `force_overlap`
    shifts the whole target body by `gap + overlap_depth` voxels along the
    stacking axis; the constant 15mm inter-body gap dominates that shift
    (only the small `overlap_depth` term, 1-4 voxels, actually varies per
    rung), so most of `unanchored_foreground_fraction`'s response on the
    mode-8 ladder is a rigid-translation artefact largely independent of
    `overlap_depth`, and its span (0.1243) nearly matches mode 1's own full
    swing (0.1291). Mode 8's own designated metric
    (`overlapping_voxel_count`) remains a clean, strictly specific isolator
    (`response(8,8)==1.0`, all its other foreign responses are 0 except a
    small 0.0347 to mode 4) — only its cross-check against metric 1 is
    coupled. Both entries are recorded in `KNOWN_CROSS_MODE_COUPLINGS` with
    their measured `cause`; `RECORDED_MARGINS[8] == 1.038` (measured
    `1.0387`, rounded down) reflects that this margin is real but thin.

- **All other measured margins are `math.inf`** (modes 1, 2, 4, 5, 7): the
  strongest possible specificity bar, because every foreign ladder's span on
  that mode's own metric was measured as exactly `0.0` — no foreign
  perturbation moved that metric at all. Mode 3's measured margin is `112.0`
  (rounded down from `112.037`) — strict, driven almost entirely by tiny
  real side-effects of `crop_at_border`/`inject_islands` on
  `rogue_island_count`'s own foreign readings, three orders of magnitude
  below its own ladder's full swing.

- **`score_harness`'s failure criteria for a non-identity `assignment`
  needed one more check beyond monotonicity/strict-change.** The negative
  control (AC18, ladder 2 scored against metric 3 and vice versa) initially
  passed for ladder 3 alone: `inject_islands` produces a tiny but genuinely
  monotonic, strictly-changing decrease in `min_dominant_component_fraction`
  (`1.0 -> 0.9986 -> 0.9971 -> 0.9957 -> 0.9943`, a real deterministic
  side-effect of extra disconnected voxels on the target label's
  `components` block), which trivially satisfies a bare monotone +
  strictly-changed check. Added a third criterion: the assigned ladder's
  `response` to its designated metric must be `>= 1.0` — i.e. this ladder
  must be at least as strong a driver of the assigned metric as that
  metric's own true ladder is for itself (`response(m, m) == 1.0` always,
  by construction, for an honest/identity assignment). Under the swap,
  `response(2, 3) == 0.0` and `response(3, 2) == 0.00752`, both far below
  `1.0`, so both ladders now correctly fail. This criterion is a no-op for
  every identity-assignment ladder (`responses[m] == 1.0` exactly, never
  `< 1.0`), so it does not affect AC13/AC14/AC17's identity-assignment
  assertions.

- **`_BASE_PARAMS` is declared locally** (`levels=("L1".."L5")`,
  `spacing=(1.0,1.0,1.0)`, `curve_amplitude_mm=6.0`) rather than importing
  `synth/corpus.py`'s private `_DEFAULT_BASE_PARAMS`, to avoid depending on
  another module's underscore-prefixed name across a package boundary; the
  values are identical (verified by AC19's `1950.0` cross-check passing) and
  `DEFAULT_LEVELS` (public) is imported from `synth/clean_gt.py` rather than
  hard-coding the level-name strings twice.

All values above were measured by running `run_severity_harness()` +
`score_harness()` against this implementation on 2026-07-26 (CPU venv, no
optional dependencies) and are reproducible via the module's `LADDER_SEED`
and pure/deterministic contract.
