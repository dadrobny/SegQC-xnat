# Seg-QC-xnat — Work Queue 003

> **Status:** ✅ Completed — superseded by queue-004 (2026-07-07).
> Step 4 of the AIDE workflow. Derived from [`../vision.md`](../vision.md),
> [`../roadmap.md`](../roadmap.md), and [`../progress.md`](../progress.md).
> Follows [`queue-002.md`](queue-002.md) (items 014, 016–025).

---

## Scope of this queue

Delivers roadmap **Stage 4 — Heuristic Rule Engine over the Failure Modes (G2)**
in full.

**Milestone delivered:** an explainable, config-driven rule engine that consumes
the complete geometric/topological feature block built in Stages 2–3 and emits,
per case, a set of **flags** — each carrying a human-readable reason, the
offending vertebra labels, and a severity — covering **every §6 failure mode**.
The flags are aggregated into the existing Stage 1 QC verdict
(`pass` / `flagged-for-review` / `fail`) and surfaced in both the JSON and
human-readable reports. Thresholds live in a documented, versioned config file so
heuristics are inspectable and tunable without code changes. On completion the
pipeline can, for each of the eight catalogued failure modes, fire at least one
heuristic on a crafted example while leaving a ground-truth fixture passing —
exactly the behaviour Stage 5 (synthetic corpus) and Stage 7 (calibration) build
on.

**Prioritisation rationale.** The roadmap graph is linear into Stage 4
(`… → 2 → 3 → 4 → 5`). Stages 2 and 3 are complete (queue-002), so the full
feature engine the heuristics depend on now exists. The Stage 1 verdict model
(`segqc/verdict.py`), report model (`segqc/report.py`), and versioned config
scaffold (`segqc/config.py`) are also already in place. Stage 4 is therefore the
single next coherent milestone: build the rule abstraction, the seven rule
families covering §6, verdict aggregation, and a shipped default config — the
"simple heuristics" core of the MVP.

### Numbering note — read before picking an item

Items 011–025 are complete. This queue continues at the next free integer and is
strictly monotonic: **026–035**.

**Estimated size:** ~1 week (10 items). Each item is independently testable
locally with `pytest` against the synthetic fixtures from item 002 and crafted
per-failure-mode inputs.

**Sequencing note.** Critical path: **026** (engine core + config model) gates
everything — every rule plugs into its `Rule`/finding abstraction. Once 026 is
merged, the seven rule-family items **027–033** are largely independent of each
other and can be picked up in parallel (each consumes already-built features and
emits findings through the 026 interface). **034** (verdict aggregation) depends
on the findings produced by 027–033. **035** (default config + CLI/report
integration + per-failure-mode end-to-end tests) depends on 034 and closes the
stage. Recommended order: 026 → (027–033 in any order/parallel) → 034 → 035.

### §6 failure-mode → rule-item coverage

| # | §6 failure mode | Covered by item |
|---|-----------------|-----------------|
| 1 | Label not aligned with the vertebra it names | 033 (mislabel/misalignment) |
| 2 | Over-/under-segmentation (fused / fragmented) | 027 (bounds), 028 (fragmentation) |
| 3 | Disconnected components / rogue islands | 028 (island/component) |
| 4 | Semantic mislabelling (wrong identification) | 033 (mislabel/misalignment) |
| 5 | Not all vertebrae segmented (missing levels) | 029 (coverage / missing levels) |
| 6 | Partial vertebra at the image border | 031 (border-partial) |
| 7 | Non-continuous label sequence | 030 (sequence continuity) |
| 8 | Overlapping segments | 032 (overlap) |

---

## Work items

### Item 026: Rule-engine core — `Rule` abstraction, finding model & config-driven runner
Establish the explainable rule-engine foundation every later rule plugs into.
Create a `segqc/heuristics/` package with: a **rule-finding data model** (a
`Finding`/`RuleResult` dataclass carrying rule id, severity, human-readable
reason, and the list of offending labels), a **`Rule` abstraction** (a callable/
registered unit that inspects the per-case feature record and yields zero or more
findings), a lightweight **registry** so rule families self-register, and a
**runner** that loads the enabled rules, executes them deterministically over the
feature block, and returns the aggregated findings. Extend the existing versioned
heuristic-config loader (`segqc/config.py`) so each rule reads its thresholds from
a documented config section (rule on/off + parameters), with sensible built-in
defaults when a key is absent.
*Testable:* unit tests register a trivial stub rule, run the engine over a
fixture feature record, and assert the finding model round-trips (id, severity,
reason, offending labels); config toggling enables/disables a rule; the runner is
deterministic and tolerates an empty rule set and a feature record with no labels
without crashing.

### Item 027: Level-aware min/max bounds rules (volume & extent)
First rule family: flag per-label **volume** and **extent** (x/y/z) that fall
outside configured **level-aware** bounds (different expected ranges for
cervical / thoracic / lumbar levels, resolved via the label convention from item
004). Each violation emits a finding with the offending label, the measured vs
expected range, and a clear reason. Bounds come from the heuristic config (026);
ship reasonable hand-set defaults (reference-derived bounds are Stage 6). Targets
§6 mode 2 (gross over-/under-segmentation).
*Testable:* unit tests assert no findings when fixture volumes/extents lie inside
bounds, a finding fires for a deliberately oversized and a deliberately
undersized label with the correct offending label and level, bounds are read from
config, and physical (mm) volumes are used so anisotropic spacing is respected.

### Item 028: Connected-components & fragmentation / island rules
Rule family over the connected-component data (item 012) and fragmentation index
(item 025): flag a label as **fragmented** when its fragmentation index falls
below a configurable threshold (a single body split into pieces), and flag
**rogue islands** when a label has small disconnected components below a
configurable voxel/volume size. Each finding names the offending label and
reports component count / sizes / fragmentation index in the reason. Targets §6
modes 2 (fragmentation) and 3 (islands).
*Testable:* unit tests assert no finding for a single-component label, a
fragmentation finding for a label split into comparable pieces, an island finding
for a dominant body plus a tiny rogue component, and that both thresholds are
config-driven; deterministic.

### Item 029: Incomplete-coverage / missing-level rules
Rule family that checks the set of present labels against the **expected ordered
level sequence** (label convention, item 004) to detect that **not all vertebrae
are segmented**: missing interior levels within the spanned range, and an
optionally configurable expected count / span. Emits findings naming the missing
levels with a human-readable reason; distinguishes a genuinely missing interior
level from an image that simply does not cover that region (border-aware, using
the border-contact flags from item 011 where relevant). Targets §6 mode 5.
*Testable:* unit tests assert no finding for a contiguous fixture spanning its
range, a missing-level finding when an interior level is removed, no spurious
finding when the range is simply truncated at the FOV edge, and that the
expected-sequence/count parameters are config-driven; deterministic.

### Item 030: Label-sequence continuity rule
Rule that consumes the inter-vertebra relationship record (item 014) to flag a
**non-continuous label sequence** — gaps, reversals, or non-anatomical jumps
(e.g. L1 → T12 → L2 → L5) — where the anatomical ordering of present labels does
not progress monotonically along the spine. Emits findings identifying the
offending labels and the nature of the discontinuity. Targets §6 mode 7.
*Testable:* unit tests assert no finding for an in-order fixture, a finding for an
injected reversal / non-anatomical jump with the correct offending labels, and
correct handling of single-label and empty cases; deterministic.

### Item 031: Border-partial-vertebra rule
Rule that uses the per-label **image-border-contact flags** (item 011) to flag
**partial vertebrae at the image border** whose appearance is truncated by the
FOV. Emits a finding per border-touching label with a reason and severity
(distinguishing an expected first/last-in-FOV truncation from a mid-spine label
unexpectedly clipped, where that distinction is available). Targets §6 mode 6.
*Testable:* unit tests assert a finding for a label touching the volume boundary,
no finding for a fully-interior label, correct offending-label attribution, and
config-driven severity/behaviour; deterministic and spacing-agnostic.

### Item 032: Overlap rule
Rule that consumes the overlap-detection results (item 015) to flag **overlapping
segments** — voxels assigned to more than one vertebra label, or labels whose
masks intersect. Emits a finding per overlapping label pair with the offending
labels and the overlap magnitude in the reason. Targets §6 mode 8.
*Testable:* unit tests assert no finding for disjoint labels, an overlap finding
for two deliberately intersecting labels with the correct pair and a sensible
magnitude, and that any minimum-overlap threshold is config-driven; deterministic.

### Item 033: Mislabel / misalignment rule
Rule family that detects a **label not aligned with the vertebra it names** and
**semantic mislabelling** by combining centroid ordering (item 014), per-vertebra
spline offset (item 018), and neighbour-consistency / monotonic-progression
metrics (item 020): flag a vertebra whose centroid is a large outlier from the
fitted spinal curve, or whose position is inconsistent with its anatomical
label's expected ordering relative to neighbours. Emits findings with offending
labels, the deviation magnitude, and a reason. Targets §6 modes 1 and 4.
*Testable:* unit tests assert no finding for a well-aligned GT fixture, a finding
for a synthetically displaced vertebra (large spline offset) and for a swapped /
mislabelled pair (ordering inconsistency) with correct offending labels, and that
deviation thresholds are config-driven; deterministic.

### Item 034: Verdict aggregation & severity
Aggregate the findings produced by all rule families (027–033) into the existing
Stage 1 **QC verdict** (`segqc/verdict.py`): map finding severities to a per-case
verdict (`pass` / `flagged-for-review` / `fail`) via a documented, config-driven
severity policy (e.g. any `fail`-severity finding ⇒ `fail`; one or more
`review`-severity findings ⇒ `flagged-for-review`; none ⇒ `pass`), preserving
per-vertebra and per-case reasons. Attach the full finding list and the derived
verdict to the case result so the report layer can render them.
*Testable:* unit tests assert the verdict mapping for: no findings (`pass`), only
review-severity findings (`flagged-for-review`), and at least one fail-severity
finding (`fail`); per-label reasons are preserved through aggregation; the
severity policy is config-driven; deterministic.

### Item 035: Default heuristic config + pipeline/report integration & per-failure-mode tests *(completes Stage 4)*
Ship a **documented, versioned default heuristic-config file** (thresholds for all
rule families, with comments/justification) and wire the rule engine into the
pipeline end-to-end: `segqc run` executes the rules over the feature block,
aggregates the verdict (034), and renders the **flags + reasons + offending
labels** into both the JSON report (`segqc/report.py`, schema extension with
validation) and the human-readable report (`segqc/human_report.py`). Add the
crafted-example acceptance tests required by the stage: at least one heuristic
fires for **each of the eight §6 failure modes**, and a ground-truth fixture
**passes** (no false flags).
*Testable:* end-to-end tests run the full pipeline on a GT fixture (asserting a
`pass` verdict and no flags) and on one crafted example per §6 failure mode
(asserting the expected rule fires with the offending labels), validate the
extended JSON against the schema, confirm the human report renders each flag's
reason, and confirm the default config loads and is versioned; deterministic /
golden-stable.

---

## Current state (2026-07-07)

✅ **Stage 4 complete.** All items **026–035 are done** (✅ in `progress.md`): the
rule-engine core + config model (026), the seven rule families (027–033), verdict
aggregation (034), and the default heuristic config with pipeline/report
integration and per-failure-mode tests (035) are all merged. Each of the eight §6
failure modes has ≥1 heuristic firing on a crafted example while a ground-truth
fixture passes. Superseded by [`queue-004.md`](queue-004.md), which delivers
Stage 5 (synthetic failure corpus & regression suite) on top of this engine.

## Next Step

Per `CLAUDE.md`: `git fetch --all --prune` and check `aide/*` branches first,
then branch per item (`aide/NNN-short-name`) and push immediately to claim it;
`git pull --rebase` before any `progress.md` edit. Start with **item 026**.
