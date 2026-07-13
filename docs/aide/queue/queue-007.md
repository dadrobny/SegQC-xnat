# Seg-QC-xnat — Work Queue 007

> **Status:** ✅ Completed — superseded by queue-008 (2026-07-13).
> Step 4 of the AIDE loop. Derived from [`../vision.md`](../vision.md),
> [`../roadmap.md`](../roadmap.md), and [`../progress.md`](../progress.md).
> Follows [`queue-006.md`](queue-006.md) (items 050–057, Stage 7 / Phase 1 — all ✅).

---

## Scope of this queue

Delivers roadmap **Stage 8 — Image-Based / Radiomics Features** in full. Stage 8
is the **first stage of "Phase 2 — Extensions"**, opened now that
[`queue-006.md`](queue-006.md) closed **Phase 1 — Complete MVP Pipeline**
(Stages 0–7, all ✅ in `progress.md`).

**This batch builds *on top of* the complete Phase-1 pipeline — it replaces
nothing.** The roadmap's scope decision (confirmed 2026-06-24) deliberately kept
Phase 1 geometric — "*richer image-based / radiomics intensity features are a
Phase 2 enhancement (Stage 8), since the catalogued failure modes are
predominantly geometric and the MVP stays minimal*." Stage 8 is that enhancement:
it is the **first use of scan voxel intensities** in the tool. Everything it plugs
into already exists and stays authoritative —

- the **geometric feature engine** (Stages 2–3, `segqc/features/*`) into which the
  new intensity features are added as an additional per-label feature family;
- the **heuristic rule engine** (Stage 4, `segqc/heuristics/*` + `runner.py`,
  `config.py`) into which the new intensity heuristic(s) are registered alongside
  the geometric rules;
- the **reference-distribution / delta-rule machinery** (Stage 6,
  `segqc/reference/*`, `segqc/heuristics/reference_delta.py`) which is *extended*
  to carry per-level intensity distributions and drive an intensity delta rule;
- the **synthetic corpus generator** (Stage 5, `segqc/synth/*`) which is *extended*
  to paint plausible/implausible CT intensities so the whole stage stays locally
  testable; and
- the **evaluation harness** (Stage 7, `segqc/eval/*`) which continues to score the
  now-intensity-aware pipeline unchanged.

**Milestone delivered:** `segqc run` gains an **image-based feature family** —
per-label first-order intensity statistics sampled from the original scan under
each vertebra mask (with an *optional* PyRadiomics path for richer texture/shape
features when the library is installed), fused into the JSON `features` block and
the per-case feature table; **≥1 intensity-based heuristic** (an
implausible-intensity flag) that fires when a labelled region's intensity is
anatomically implausible for bone; and **reference distributions extended with
intensity features** so a level-aware **delta-to-reference intensity rule** grounds
those judgements in VerSe-derived expectations rather than hand-guessed HU
constants. On completion the Stage 8 acceptance criterion holds: image features are
computed on fixtures, ≥1 intensity heuristic fires appropriately, and the suite is
green.

**Prioritisation rationale.** Stage 8 is the **only unblocked Phase-2 stage**: its
roadmap dependencies are **Stages 2 and 6**, both ✅. The other Phase-2 stages are
either independent deployment/perf work (Stage 9 XNAT, Stage 10 GPU — sequenced
after, and better tackled as their own cohesive batches) or explicitly depend on
Stage 8's image features (Stage 11 extensibility/classification lists "*Stage 8 for
image features*" among its dependencies). Doing image features first therefore
unblocks the most downstream work while extending the pipeline along the grain the
vision already anticipated (§5.2 "Image-based", §7.2 "a radiomics library e.g.
PyRadiomics"). The queue is scoped to **exactly Stage 8** and **stops at the stage
boundary** — Stage 9 (containerisation) onward is a fresh batch behind the next
human-reviewed queue PR.

**Local-testability note (key design decision).** Every prior stage consumed only
the **label map**; the scan was loaded (`segqc/io.py`) but its voxel intensities
were never read, so the repo has **no intensity-bearing scan fixtures**. Stage 8
therefore starts (item **058**) by extending the Stage 5 synthetic generator
(`segqc/synth/*`) to **paint controlled CT-like intensities** into the clean-GT
label regions — bone-plausible Hounsfield-unit ranges in vertebra bodies, with
derived variants carrying *implausible* intensities (e.g. a region filled with
soft-tissue / air / metal-bright HU) to exercise the heuristic. This keeps the
entire stage deterministic under `pytest` **without shipping VerSe or any external
CT** (mirroring the synthetic-cohort decisions of queues 005/006). Running against
**mounted real VerSe scans** for the reference-distribution extension (063) remains
a documented, reproducible path, exactly as the Stage 6 mounted-VerSe path is. The
**optional PyRadiomics** dependency (059→060) is isolated behind an optional-import
adapter so the default suite runs with PyRadiomics *absent* (first-order features
only) and a small guarded test exercises the present path when it is installed.

### Numbering note — read before picking an item

Items 001–057 are complete (Stages 0–7, all ✅ in `progress.md` — Phase 1
complete). This queue continues at the next free integer and is strictly
monotonic: **058–065**.

**Estimated size:** ~1 week (8 items, within `loop.queue_cap = 10`). Each item is
independently testable locally with `pytest`: the fixture/extractor items assert
per-label intensity statistics against hand-computed values on tiny painted
fixtures; the adapter item asserts graceful degradation when PyRadiomics is absent
and correct values when present; the fusion/heuristic/reference items assert
schema-valid output, correct rule firing **and** non-firing, and reference
round-tripping; the integration item asserts the Stage 8 acceptance criteria
end-to-end.

**Sequencing note.** Critical path:
**058** (intensity-bearing synthetic fixtures) is the shared foundation and should
merge first — every downstream item is tested against it. **059** (first-order
intensity extractor) is the core deliverable and depends on 058. After 059, four
items parallelise: **060** (optional PyRadiomics adapter), **061** (report
fusion), **062** (implausible-intensity heuristic), and **063** (reference
distributions extended with intensity) all depend on 059 and are otherwise
mutually independent. **064** (delta-to-reference intensity rule) depends on **063**
(the extended reference artifact) and the rule infrastructure. **065**
(integration + acceptance) depends on everything and closes Stage 8. Recommended
order: 058 → 059 → (060 ‖ 061 ‖ 062 ‖ 063) → 064 → 065.

### Stage-8 deliverable → item coverage

| Stage-8 deliverable | Delivered by item(s) |
|---------------------|----------------------|
| Intensity features over each labelled region (+ original scan); optional **PyRadiomics** integration | 059 (per-label first-order intensity extractor), 060 (optional PyRadiomics adapter) — enabled for local testing by 058 (intensity-bearing fixtures) |
| Feature **fusion into the report** + ≥1 intensity-based heuristic (e.g. implausible-intensity flag) | 061 (fusion into `features` block + feature table), 062 (implausible-intensity heuristic) |
| Reference distributions **extended with intensity features** | 063 (reference aggregation/artifact extended with per-level intensity distributions), 064 (level-aware delta-to-reference intensity rule) |
| *(test enablement & acceptance closure)* image features computed on fixtures; ≥1 intensity heuristic fires appropriately; tests pass | 058 (fixtures), 065 (integration into `segqc run` + Stage 8 acceptance suite) |

Every deliverable is realised by ≥1 item. Item 058 is the fixture foundation that
makes image features locally testable; item 065 wires extractor → fusion →
heuristics → reference-delta into `segqc run` and asserts the stage's acceptance
criterion end-to-end.

---

## Work items

### Item 058: Intensity-bearing synthetic scan fixtures (HU-painted GT + implausible variants)
Extend the Stage 5 synthetic generator (`segqc/synth/*`, e.g. a new
`segqc/synth/intensity.py`) to produce a **scan volume co-registered with the
clean-GT label map** by painting controlled CT-like **Hounsfield-unit** intensities
into each labelled region: bone-plausible ranges in vertebra bodies (with mild
per-voxel/per-level variation) over a soft-tissue/air background, on the **same
grid, spacing and affine** as the label map. Provide derived **implausible-intensity
variants** (e.g. a chosen vertebra filled with soft-tissue-low or metal-bright HU)
for exercising the intensity heuristic, and wire these into the committed fixture
set / corpus builder so downstream items have deterministic inputs. Pin any newly
committed byte-reproducible fixture per the CLAUDE.md `.gitattributes` LF/`binary`
gotcha. No feature extraction or heuristics here — just reproducible scan+label
inputs.
*Testable:* the generator emits a scan whose intensities, sampled under each label,
fall in the intended per-region HU ranges; the implausible variants differ only in
the targeted region's intensities (label map byte-identical to the clean GT);
scan/label affine and shape match exactly; output is deterministic across repeated
runs (seeded), and any committed fixture is byte-stable on re-generation.

### Item 059: Per-label first-order intensity feature extractor
Add the core **image-based feature family** (deliverable 1): a pure, spacing-aware
module (e.g. `segqc/features/intensity.py`) that, given the **scan array + label
map** (+ affine/spacing from `segqc/io.py`), samples the scan voxels under each
vertebra mask and computes **per-label first-order intensity statistics** —
mean, median, std, min, max, a documented set of percentiles, range/IQR, and
intensity entropy — over a documented tracked-feature set. Guard the scan↔label
**grid alignment** explicitly (matching shape/affine required; mismatch reported,
not silently mis-sampled), and handle empty labels, all-background masks, and
NaN/inf voxels with well-formed sentinels rather than crashes. Pure NumPy/SciPy,
no PyRadiomics, no file I/O — arrays in, per-label features out.
*Testable:* on a hand-built scan+mask, per-label mean/median/std/percentiles match
hand-computed values; a label covering a uniform-intensity region yields that
intensity with zero variance; anisotropic spacing does not corrupt intensity
statistics; an empty label and a NaN-containing region yield documented sentinels
rather than errors; deterministic.

### Item 060: Optional PyRadiomics integration behind an optional-import adapter
Add the **optional PyRadiomics** path (deliverable 1) behind a capability/adapter
boundary (e.g. `segqc/features/radiomics.py`) that, **when PyRadiomics is
importable**, computes a documented subset of richer radiomics features (e.g.
first-order + a texture family such as GLCM, and shape) per label from the same
scan+mask, and **when it is absent cleanly degrades** to the item-059 first-order
features only — never a hard failure and never a hard dependency (PyRadiomics stays
an optional extra in `pyproject.toml`, consistent with the vision's "GPU/heavy libs
never required" stance). Normalise PyRadiomics output into the same per-label
feature shape item 059 emits so downstream fusion is source-agnostic, and record
which backend produced each feature (provenance) for reproducibility.
*Testable:* with PyRadiomics **absent** (default CI), the adapter returns the
first-order feature set and a flag indicating radiomics unavailable — no import
error; with PyRadiomics **present** (a guarded/skippable test), the documented
radiomics features are produced in the normalised shape and are deterministic;
provenance/back-end marker is correct in both paths.

### Item 061: Fuse intensity features into the JSON report & per-case feature table
Wire the intensity feature family (059, and 060 when available) into the **feature
engine and report** (deliverable 2 — fusion): extend the feature aggregation
(`segqc/features/__init__.py`) so `segqc run` computes intensity features when a
scan is present, add them to the versioned JSON **`features` block**
(`segqc/report.py`, bumping the schema/`features` version as needed) and to the
per-case **feature table** (`segqc/feature_report.py`) and human report. Degrade
gracefully when no scan / no intensity backend is available (geometric-only output
stays valid, intensity fields marked unavailable rather than omitted-ambiguously).
Keep serialisation deterministic and schema-valid.
*Testable:* running the pipeline on an intensity-bearing fixture emits per-label
intensity features in the JSON `features` block and the feature table, validating
against the (bumped) schema; a run with no scan / intensity backend still produces
a valid report with intensity fields marked unavailable; output is byte-stable
across repeated runs; existing geometric-feature tests remain green.

### Item 062: Implausible-intensity heuristic (intensity-based rule)
Add the **≥1 intensity-based heuristic** the stage requires (deliverable 2): a
config-driven rule (e.g. `segqc/heuristics/intensity.py`) registered in the rule
engine (`segqc/heuristics/runner.py`) that flags a labelled region whose intensity
statistics are **implausible for a vertebra** — e.g. mean/median HU outside a
documented level-agnostic bone-plausibility band (too low ⇒ soft-tissue/air
mislabel; implausibly bright ⇒ metal/implant), emitting a finding with a
human-readable reason and the offending label(s), per the Stage 4 finding contract.
Thresholds live in the versioned heuristic config (`segqc/config.py`) with
documented defaults; the rule participates in verdict aggregation like every other
rule.
*Testable:* on the clean HU-painted fixture the rule **does not fire** (bone-plausible
intensities pass); on the implausible-intensity variant (058) it **fires** on
exactly the targeted label with a reason + offending label; thresholds are read
from config (overriding them changes firing); a case with no intensity features
produces no spurious intensity finding; deterministic firing **and** non-firing.

### Item 063: Extend reference distributions with per-level intensity features
Extend the Stage 6 reference machinery (deliverable 3): teach the VerSe ingestion /
aggregation (`segqc/reference/ingest.py`, `aggregate.py`, `schema.py`,
`artifact.py`) to compute and store **per-level intensity feature distributions**
(mean/percentiles per tracked intensity feature, stratified by vertebra level)
alongside the existing geometric distributions, **bump the reference-artifact
schema version**, and rebuild the versioned artifact via the builder script. Ingestion
must require a scan alongside each GT label map for the intensity distributions and
remain backward-tolerant (geometric-only reference still loads). Keep the artifact
byte-reproducible and pinned per the CLAUDE.md `.gitattributes` gotcha.
*Testable:* aggregating a small synthetic GT+scan cohort produces per-level
intensity distributions with hand-verifiable summary stats; the artifact schema
version is bumped and the extended artifact round-trips (build → load → same
values); an intensity-less (geometric-only) reference still loads under the new
schema; the artifact regenerates byte-identically from fixed inputs.

### Item 064: Level-aware delta-to-reference intensity rule
Complete deliverable 3's reference grounding: extend the delta-to-reference rule
(`segqc/heuristics/reference_delta.py`) so **intensity features participate** in
level-aware out-of-range / distribution-distance detection driven by the extended
reference artifact (063) — a vertebra whose intensity deviates from its level's
reference distribution beyond a documented threshold is flagged, with the reason
citing the reference (mirroring the existing geometric delta rule). Thresholds are
config-driven (`segqc/config.py`); the rule is inert when the loaded reference
carries no intensity distributions (backward compatibility).
*Testable:* a GT-consistent vertebra intensity falls **within** its level's
reference band (no flag); a vertebra with reference-deviant intensity is flagged
with a reference-citing reason on the correct label; a reference artifact lacking
intensity distributions makes the intensity delta rule inert (no crash, no spurious
flag); thresholds read from config; deterministic firing and non-firing.

### Item 065: Stage 8 integration & acceptance suite *(completes Stage 8)*
Close Stage 8 by wiring the image-feature family end-to-end into `segqc run` —
extractor (059) + optional radiomics (060) → report fusion (061) → intensity
heuristic (062) → delta-to-reference intensity rule (064) — behind documented
versioned-config knobs (enable/disable intensity features & rules), and add the
**Stage 8 acceptance suite** asserting the roadmap criterion: image features are
**computed on fixtures**, **≥1 intensity-based heuristic fires appropriately**
(fires on the implausible variant, silent on clean GT), and the full suite passes.
Document the optional-PyRadiomics and mounted-VerSe (intensity reference) paths, and
update `progress.md` Stage 8 to reflect completion. No new feature/rule logic here —
this is the reproducible wiring + acceptance closure.
*Testable:* `segqc run` on an intensity-bearing fixture emits intensity features
and, on the implausible variant, an intensity-based flag with reason — end-to-end
through the CLI; the acceptance suite is green (features present, heuristic fires on
implausible / silent on clean, geometric behaviour unchanged); config knobs toggle
the intensity path; output is schema-valid and byte-stable across repeated runs.

---

## Current state (2026-07-13)

✅ Completed. All items 058–065 merged; **Stage 8 — Image-Based / Radiomics
Features** is done, closing the first stage of Phase 2. Superseded by
[`queue-008.md`](queue-008.md) (Stage 9 — Containerisation & XNAT Container
Service Command).

| Item | Status |
|---|---|
| 058 Intensity-bearing synthetic scan fixtures | ✅ done |
| 059 Per-label first-order intensity feature extractor | ✅ done |
| 060 Optional PyRadiomics integration | ✅ done |
| 061 Fuse intensity features into the JSON report | ✅ done |
| 062 Implausible-intensity heuristic | ✅ done |
| 063 Extend reference distributions with intensity | ✅ done |
| 064 Level-aware delta-to-reference intensity rule | ✅ done |
| 065 Stage 8 integration & acceptance suite | ✅ done |

## Next Step

Per `CLAUDE.md`: `git fetch --all --prune` and check `aide/*` branches first, then
branch per item (`aide/NNN-short-name`) and push immediately to claim it;
`git pull --rebase` before any `progress.md` edit. Start with **058**, then
**059**. Two ways to proceed: spec the whole queue now with `/aide-spec-queue 007`
in one interactive sitting, or spec per-item during execution via
`/aide-run-queue 007`.
