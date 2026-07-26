# FACET — Work Queue 013

> **Created:** 2026-07-26
> Step 4 of the AIDE loop · derived from [`../vision.md`](../vision.md),
> [`../roadmap.md`](../roadmap.md), and [`../progress.md`](../progress.md) ·
> each item below is specced into [`../items/`](../items/) and tracked in
> `../progress.md` (queue state is derived there, never declared here).
> Opens **Stage 17**; supersedes the completed [`queue-012.md`](queue-012.md)
> (Stage 14, closed 2026-07-19).

---

## Scope of this queue

Delivers roadmap **Stage 17 — Foreign-Convention Interop & Orientation-Safe
Image Layer** (G2, G6) in full: the first stage after the 2026-07-25
supersession. Today `segfacet.labels` defines its own vertebra numbering —
**25 = `S`, 26 = `Cocygis`, 29 = `L6`** — while the TPTBox convention that
**SPINEPS** (the new primary reference segmenter) emits reads **25 = `L6`,
26 = `S1`, 29 = `S2`** (confirmed against `TPTBox/core/vert_constants.py`'s
`v_idx2name`; only 28 = `T13` agrees). Feeding SPINEPS output through the
current defaults **silently misreads the sacrum as L6** — no error, plausible
numbers, wrong — so this must land before any real-segmenter number is
computed by Stage 16 or the Stage 19–21 audit chain.

**Why this queue is scoped to exactly one stage.** Stage 17 alone comes to
five items — already a meaningful fraction of `loop.queue_cap = 10` — and
Stage 18 (the next roadmap unit) explicitly depends on Stage 17 landing first
("level names must be right before per-level metrics mean anything"). Queuing
both would risk a queue that outgrows review size and blurs the stage
checkpoint the create-queue convention exists to preserve.

**Prioritisation & sequencing.** The label-convention swap (093) is
independent, cheap, and unblocks everything downstream that touches level
names, so it goes first. The image-layer migration (094) and the
environment/dependency migration (095) are the two structural changes — 094
depends on TPTBox being installable, which 095 also touches (TPTBox's own
numpy-1/numpy-2 split is what motivates the `>=3.11` / `numpy<3` range), so
095 is sequenced right after 093 and before 094 to avoid installing TPTBox
against an environment about to be replaced. The run-manifest schema (096) is
independent of 093–095 and may run in parallel. Item 097 closes the stage and
must run last. Recommended order: **093 → 095 → 094 → 096 → 097**.

**Key constraint — TPTBox becomes a required core dependency, not an
optional/gated one.** The roadmap's own wording — "replacing the hand-rolled
`_spacing_from_affine`" — means the image layer's *default* path changes, not
an optional extra alongside it (unlike `pyradiomics`/`cupy`, which stay
opt-in). `Volume`/`Case` (the two frozen dataclasses in `segfacet.io`) stay
the public shape every one of the ~22 nibabel-importing modules already
depends on, so TPTBox sits underneath `io.py` behind that seam rather than
leaking into feature/rule modules.

**Key constraint — no real SPINEPS output is committed anywhere in this repo
today.** Item 097's "real segmenter output round-trips" acceptance criterion
is therefore environment-gated on a data-presence check (mirroring the
`SEGFACET_VERSE_COHORT` / `requires_verse` pattern already used in
`tests/test_091_stage14_acceptance.py`, not a package-presence `[validation]`
profile) and must skip cleanly — never fail — when no fixture path is
supplied, recording `❓ Unverified` per `.aide/conventions.md`'s
environment-gated rule.

**Numbering.** Continues at the next free integer: **093–097**.

### Stage-17 deliverable → item coverage

| Stage-17 deliverable | Delivered by item |
|---|---|
| Adopt TPTBox vertebra standard as default; retire legacy table; keep `LabelConvention` overridable | 093 |
| Environment migration (`requires-python >=3.11`, numpy range, `constraints.txt`, numpy-major CI leg) | 095 |
| TPTBox-backed orientation-safe image layer (`Volume`/`Case` over TPTBox `NII`) | 094 |
| Run-manifest schema (segmenter version/SHA, weights hash, seed, dataset id, resolved versions) | 096 |
| Stage validation + verification-row closure | 097 |

---

## Work items

### Item 093: Adopt the TPTBox vertebra label convention as default

Replace `segfacet.labels`'s `DEFAULT_LABEL_MAP` and `CANONICAL_ORDER` with the
TPTBox vertebra table (`TPTBox.core.vert_constants.v_idx2name`, **filtered to
the 1–33 vertebra range** — the raw dict is merged with ~40+ `Location`
subregion names that must not leak in), retiring the legacy
25=`S`/26=`Cocygis`/29=`L6` table. `LabelConvention` (`labels.py:139-266`) is
already a fully-replacing, immutable abstraction reached via
`LabelConvention.from_mapping(...)`, so this is a data swap at the
`DEFAULT_LABEL_MAP`/`CANONICAL_ORDER` source, not new plumbing; the 15 modules
that import `labels` consume the convention object, not the raw table, so no
call site should need to change. *Testable:* a regression test asserts labels
25/26/28/29 resolve to `L6`/`S1`/`T13`/`S2` (TPTBox) rather than
`S`/`Cocygis`/`T13`/`L6` (legacy); the committed `reference_verse_v1.json`
(keyed by vertebra **name**, not integer) loads and scores an unchanged GT
fixture identically before/after the swap — proving no re-fit of the
80-subject VerSe19 distribution was required; the existing label/heuristic
test suite stays green with only the expected label-name changes.

### Item 095: Environment migration — Python 3.11+ and a numpy range

Raise `requires-python` from `>=3.9` to `>=3.11` in `pyproject.toml`, replace
the unbounded `numpy>=1.21` lower bound with a range (`numpy>=1.26,<3`),
regenerate `constraints.txt`'s single `numpy==2.0.2` pin into something
compatible with the range, and add a CI leg that runs the suite against both
a numpy-1.26.x and a numpy-2.x install (today's `ci.yml` has exactly one
`test` job pinned to the single `constraints.txt` numpy; no numpy-major matrix
exists). The floor and range are chosen to match TPTBox's own split
(`python<3.11` → `numpy<2.0`, `python>=3.11` → `numpy>=2.0,<3.0`), so pinning
FACET to `>=3.11` avoids straddling TPTBox's internal branch. Land this before
item 094 installs TPTBox, so TPTBox is installed once against the final
environment rather than twice. *Testable:* `pip install -e .[dev] -c
constraints.txt` succeeds on a Python 3.11 host; the new CI job matrix runs
the full suite green on both numpy majors; a `python<3.11` install is
rejected with a clear `requires-python` error rather than a downstream
failure.

### Item 094: TPTBox-backed orientation-safe image layer

Add TPTBox as a required core dependency and back `segfacet.io`'s
`Volume`/`Case` loading with TPTBox's `NII` class
(`NII.load`/`.reorient`/`.rescale`/`.resample_from_to`/`.zoom`/`.affine`),
replacing the hand-rolled `_spacing_from_affine` (`io.py:109-116`, currently a
thin wrapper over `nib.affines.voxel_sizes`) with TPTBox's orientation-safe
equivalents. `Volume`/`Case` keep their existing public field shape
(`data`, `spacing`, `affine`, `path`) so the ~22 modules that currently
`import nibabel` need no changes — TPTBox sits behind the `io.py` seam.
*Testable:* existing I/O and pipeline tests stay green with byte-for-byte
equivalent `spacing`/`affine` values on the committed fixtures; a new fixture
saved in a non-canonical axis order (e.g. `LPS` rather than `RAS`) loads with
correct spacing/affine under the TPTBox path where the old nibabel-only path
would have silently mis-oriented it; a full `segfacet run` on a synthetic
fixture produces byte-identical (within the existing numeric tolerance)
features to the pre-migration output.

### Item 096: Run-manifest provenance schema

Add a run-manifest record — segmenter version/SHA, weights hash,
post-processing toggles, seed, dataset id, and the resolved `numpy`/`TPTBox`
versions — carried alongside pipeline output, following the existing
`EvaluationProvenance` pattern in `eval/report.py` (frozen dataclass +
`.to_dict()` + JSON-schema validation, written via `Path.write_bytes` per the
repo's byte-reproducibility convention) rather than inventing a new shape.
Wire optional CLI flags into `segfacet run`/`evaluate` to populate the
segmenter-identifying fields (all optional — a run without a real segmenter
behind it, e.g. against GT, simply omits them); include the manifest block in
the JSON report when populated. *Testable:* the manifest dataclass
round-trips through `to_dict()`/JSON-schema validation with all fields
populated and with all-optional-fields-omitted; a `segfacet run` invocation
with the new flags emits a `run_manifest` block in its JSON report; an
invocation without them omits the block cleanly (no crash, no empty stub).

### Item 097: Validate stage 17: Foreign-Convention Interop & Orientation-Safe Image Layer

Replay Stage 17's use cases end-to-end, not just the unit suite. Run a full
`segfacet run` through the TPTBox-backed image layer (item 094) using the
TPTBox-default label convention (item 093) on both a committed synthetic
fixture and — gated on a `SEGFACET_SPINEPS_FIXTURE` (or equivalently-named)
environment variable supplying a real SPINEPS output path, mirroring the
`SEGFACET_VERSE_COHORT`/`requires_verse` pattern in
`tests/test_091_stage14_acceptance.py` — a real SPINEPS-labeled case,
confirming level names round-trip correctly end-to-end (not just at the
`labels.py` unit level). Confirm the numpy-major CI matrix (item 095) is
green on both legs. Flip the "real segmenter output round-trips" acceptance
criterion and any Environment-Gated Capability Verification row this stage
introduces to ✅ Verified where a real SPINEPS fixture is available in the
running environment; otherwise record it ❓ Unverified with the reason
(no committed real-segmenter fixture exists yet — that is Stage 16's job),
never a silent pass. *Testable:* the end-to-end run produces a valid JSON +
human report on the synthetic fixture through the full TPTBox-backed path;
the SPINEPS-gated case either runs and asserts correct level names, or skips
cleanly with a recorded skip reason when the fixture env var is unset; the
numpy-major CI legs are confirmed green; `progress.md`'s Stage 17 section and
the Environment-Gated Capability Verification table are updated to reflect
what was actually exercised.

---

## Current state (2026-07-26)

Generated after the 2026-07-25 minimal supersession opened Stages 17–21 and
closed the loop's queue backlog (Stage 14 was the last queued/completed work,
via [`queue-012.md`](queue-012.md)). Opens **Stage 17 — Foreign-Convention
Interop & Orientation-Safe Image Layer**, the first of the post-supersession
stages and a hard dependency for Stage 18 (per-mode metrics need correct
level names first). Stages 19 and 20 are pure audit work (no production
behaviour touched) and may be queued and run alongside 17/18 rather than
strictly after them, per the roadmap's post-supersession framing — but this
queue stays scoped to Stage 17 alone to keep the batch reviewable and to let
Stage 17's landing inform how 18/19/20 are split. Stage 16 (real failure
corpus) and Stage 21 (real-GT perturbation corpus) remain blocked behind this
chain and are not yet queueable.
