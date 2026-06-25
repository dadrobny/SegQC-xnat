# Item 004 — Label-Convention Module

> **Status:** 📋 Planned · **Created:** 2026-06-25
> **Stage:** 0 — Project Scaffolding & I/O Foundation
> **Queue:** [`../queue/queue-001.md`](../queue/queue-001.md) · Item 004
> **Objectives:** Foundation (tool-agnostic label→anatomy normalisation for G1–G4)
> **Suggested branch:** `aide/004-label-convention`

---

## Description

Implement the configurable mapping between **integer labels** and **anatomical
vertebrae** (C1–C7, T1–T12(+T13), L1–L5(+L6), S, …), shipping a **default
TotalSegmentator / VerSe** mapping and allowing an override via config. Provide
lookups in **both directions** (label value → anatomical name, and name → label
value) and a **label-inventory summariser** that turns the raw `{label: count}`
inventory produced by the loader (item 003) into a human-meaningful summary of
present vertebrae, with explicit **unknown-label handling** (out-of-range or
unmapped integers must never crash).

This item sits on the **critical path** (`001 → 003 → 004 → 006`). Item 003 has
landed the loader (`src/segqc/io.py`), which already exposes a raw, anatomy-free
`Case.label_inventory` (`{label_value: voxel_count}`, background `0` excluded).
This item produces the *anatomy layer* on top of that raw inventory: item 006
(CLI `run`) will print the label inventory **with anatomical names** using this
module, and Stage 2+ feature/heuristic code (level-aware centroids, "missing
levels", sequence-continuity rules) all key off anatomical level identity rather
than raw integers.

The mapping is **tool-agnostic** by design (vision §4, §5.1): the tool operates
on a *documented label convention*, not on any one segmenter's internals. The
default convention is TotalSegmentator/VerSe, but a caller must be able to
override it (e.g. a segmenter that numbers vertebrae differently) without code
changes.

### Scope boundary (what this item does *not* do)

To avoid overlap with adjacent items:

| Concern | Owned by | This item |
|---|---|---|
| NIfTI load + raw `{label: count}` inventory | Item 003 | **consumes** the raw inventory; does not load files |
| Logging framework / heuristic-config file loader | Item 005 | raises plain exceptions; ships an in-code default mapping + an optional dict/config override; **no** YAML/JSON file loader of its own |
| Wiring inventory printing into the CLI `run` body | Item 006 | provides the summariser API; does **not** edit `cli.py` |
| Level-aware geometric features (centroids, ordering) | Stage 2 | provides only the *name ↔ value ↔ ordinal* convention they will key off |
| "Missing levels" / sequence-continuity **verdicts** | Stage 4 | exposes the canonical ordered level sequence as data; makes **no** pass/fail judgement |
| Per-case verdict / report model | Stage 1 (008–010) | returns a plain summary object/strings; no verdict |

### Config override without item 005

Item 005 (the versioned heuristic-config file loader) is **not** a prerequisite
here, and this item must not pre-empt it. The override mechanism for this item is
therefore an **in-memory mapping passed to the convention constructor** (a
`Mapping[int, str]`), *not* a YAML/JSON file format. When item 005 lands, a
follow-up can let the heuristic config *carry* such a mapping and hand it to this
module — but defining the on-disk config schema is item 005's job, not this one.

---

## Acceptance Criteria

- [ ] A label-convention module exists (proposed `src/segqc/labels.py`) exposing a
      documented public surface: a `LabelConvention` type (finalised in
      Decisions), a ready-made **default** instance/factory carrying the
      TotalSegmentator/VerSe mapping, and a label-inventory **summariser**.
- [ ] **The default TotalSegmentator/VerSe mapping** is shipped in code and covers
      the full cervical/thoracic/lumbar/sacral range **including the transitional
      vertebrae** named in the vision (C1–C7, T1–T12, **T13**, L1–L5, **L6**, and
      the sacrum **S**). The exact integer↔name table is recorded in Decisions.
- [ ] **Bidirectional lookup**: name→value and value→name, each total and
      side-effect-free. value→name returns a clear "unknown" sentinel (not an
      exception, not a silent wrong answer) for an unmapped integer; name→value
      raises a clear error (or returns `None` per Decision) for an unknown name.
      Name lookup is case-insensitive / normalised per Decision.
- [ ] **A custom override applies**: constructing a `LabelConvention` from a custom
      `Mapping[int, str]` makes lookups use the override, fully replacing (or
      layering on, per Decision) the default — verified by a test where an
      override remaps an integer to a different name and both directions reflect
      it.
- [ ] **Default mapping round-trips**: for every entry in the default table,
      `name_of(value_of(name)) == name` and `value_of(name_of(value)) == value`
      (the table is a bijection; this is asserted in tests).
- [ ] **Label-inventory summariser**: given the loader's raw
      `{label_value: voxel_count}` (or a `Case`), produce a summary that maps each
      present label to its anatomical name and voxel count, and **separates
      recognised from unknown** labels. Unknown / out-of-range labels are surfaced
      explicitly (e.g. an `unknown` list) — **never** dropped silently and
      **never** crashing.
- [ ] **Unknown / out-of-range labels are handled gracefully** across the whole
      surface: negative integers, very large integers, and integers with no
      mapping all produce the "unknown" outcome without raising (except where an
      explicit raising API is documented). Tests cover each.
- [ ] **An ordered level sequence** (canonical anatomical ordering C1→…→S) is
      exposed as data, so later "missing level"/continuity logic (Stage 2/4) and
      the summariser can present levels in anatomical order rather than integer
      order. (Integer order need not equal anatomical order; see Decisions.)
- [ ] **Clear, typed errors** where this module raises (e.g. duplicate names in a
      user override, or unknown-name lookup if the raising variant is chosen): a
      small dedicated exception type (proposed reuse of `SegQCInputError` from
      `io.py`, or a new `LabelConventionError` — decided below) rather than a bare
      `KeyError`/`ValueError` leaking.
- [ ] Unit tests cover: default round-trip (bijection), custom override applies in
      both directions, unknown/out-of-range handling on every entry point, the
      summariser over a populated fixture **and** the empty fixture, and the
      ordered-sequence accessor. Tests run against the item 002 synthetic
      fixtures where useful.
- [ ] Pure-Python, CPU-only, no new third-party dependency; imports stay cheap
      (`import segqc.labels` pulls in nothing heavier than NumPy, and ideally only
      the stdlib + typing). Identical behaviour on Windows/macOS/Linux.

---

## Implementation Steps

1. **Confirm the public API surface** (see Decisions). Proposed:
   ```
   src/segqc/labels.py
     # (optional) class LabelConventionError(Exception): ...   # or reuse SegQCInputError
     DEFAULT_LABEL_MAP: dict[int, str]      # TotalSegmentator/VerSe, value -> name
     CANONICAL_ORDER: tuple[str, ...]       # C1..C7,T1..T13,L1..L6,S in anatomical order
     UNKNOWN = "unknown"                    # sentinel name for unmapped values

     @dataclass(frozen=True)
     class LabelConvention:
         value_to_name: Mapping[int, str]
         # derived: name_to_value
         def name_of(self, value: int) -> str: ...          # -> name or UNKNOWN
         def value_of(self, name: str) -> int | None: ...   # -> value or None/raise
         def is_known(self, value: int) -> bool: ...
         @classmethod
         def default(cls) -> "LabelConvention": ...
         @classmethod
         def from_mapping(cls, m: Mapping[int, str], *, base: ... ) -> "LabelConvention": ...

     @dataclass(frozen=True)
     class InventorySummary:
         recognised: list[tuple[int, str, int]]   # (value, name, count), anatomical order
         unknown:    list[tuple[int, int]]         # (value, count)
         # convenience: present_levels, n_recognised, n_unknown, etc.

     def summarise_inventory(
         inventory: Mapping[int, int],
         convention: LabelConvention = ...,
     ) -> InventorySummary: ...
   ```
2. **Author the default map** (`DEFAULT_LABEL_MAP`) from the
   TotalSegmentator/VerSe convention (see Decision 2 for the exact table) and the
   `CANONICAL_ORDER` tuple. Assert at construction (or in a test) that the default
   is a bijection (no duplicate names, no duplicate values).
3. **Implement `LabelConvention`**:
   - Build the reverse `name_to_value` map at construction; validate the user
     mapping for duplicate names and raise a clear, typed error if found.
   - `name_of(value)` returns the mapped name or `UNKNOWN`; `value_of(name)`
     normalises the name (case / whitespace) and returns the value or `None`/raises
     per Decision; `is_known(value)` is the boolean form.
   - Normalise stored names to a canonical case so lookups are robust.
4. **Implement the summariser** `summarise_inventory`:
   - Accept the loader's `{label: count}` mapping (and a convenience overload/path
     for a `Case`, per Decision) plus an optional convention (defaulting to the
     shipped default).
   - Partition present labels into **recognised** (mapped) and **unknown**
     (unmapped), attach names + counts, and order the recognised entries by
     `CANONICAL_ORDER`.
   - Never raise on unknown labels; surface them in the `unknown` collection.
5. **Error handling**: a single dedicated exception type for the few raising paths
   (duplicate-name override; optionally unknown-name lookup). Decide between a new
   `LabelConventionError` and reusing `io.SegQCInputError`; record it.
6. **Docstrings + type hints** on all public symbols; keep imports cheap. Do not
   import SciPy/skimage/NiBabel here (the summariser takes a plain mapping; if a
   `Case` convenience is added, import `segqc.io` lazily/at type-check only).
7. **Tests** in `tests/test_labels.py` using the item 002 synthetic fixtures
   (`labelled_blocks`, `empty_labelmap`, `anisotropic`) and small inline maps for
   the unknown/override cases. No edits to `cli.py` (item 006) or `io.py`.
8. **Verify** the manual validation checklist (clean venv, `pytest`, REPL check).

---

## Testing Strategy

- **Framework:** `pytest` (wired by item 001; synthetic fixtures from item 002 are
  on `main`). Use the shared fixtures from `tests/conftest.py`.
- **Fixtures:** `labelled_blocks` (labels {1,2,3}), `empty_labelmap` (no labels),
  `anisotropic` (labels {1,2}). For unknown/override cases, build small inline
  `{int: int}` inventories directly in the test (no NIfTI needed — the summariser
  takes a plain mapping).
- **Tests authored here (illustrative):**
  - `test_default_round_trips` — for every entry in `DEFAULT_LABEL_MAP`, both
    directions invert; the default is a bijection (unique names, unique values).
  - `test_default_covers_transitional` — C1–C7, T1–T13, L1–L6, S are all present
    and ordered correctly in `CANONICAL_ORDER`.
  - `test_value_to_name_known` / `test_name_to_value_known` — spot-check a few
    levels (e.g. the cervical start, a thoracic mid, the sacrum).
  - `test_value_to_name_unknown_returns_sentinel` — unmapped / negative / huge
    integers return `UNKNOWN` (and `is_known` is `False`) without raising.
  - `test_name_to_value_unknown` — an unknown name returns `None` / raises per
    Decision; case-insensitive lookup of a known name succeeds.
  - `test_custom_override_applies` — a `LabelConvention.from_mapping({...})`
    remaps an integer to a new name; both directions reflect the override.
  - `test_override_duplicate_name_raises` — an override with two values mapping to
    the same name raises the dedicated typed error.
  - `test_summarise_labelled_blocks` — summarising the `labelled_blocks` inventory
    yields the expected `(value, name, count)` recognised entries in anatomical
    order and an empty `unknown` list.
  - `test_summarise_with_unknown_label` — an inventory containing a mapped label
    **and** an out-of-range label splits them into `recognised` / `unknown`
    correctly; nothing is dropped.
  - `test_summarise_empty` — the `empty_labelmap` inventory summarises to empty
    `recognised` and empty `unknown` (no crash on zero foreground).
- **Determinism / portability:** all inputs are in-process plain mappings or the
  deterministic item 002 fixtures; no network, no GPU, no committed binaries.
  Pure-Python — identical on all three OSes.

---

## Dependencies

- **Upstream (blocks this item):**
  - Item 001 (package skeleton, pytest) — **complete** (on `main`).
  - Item 002 (synthetic fixtures, `tests/conftest.py`) — **complete** (on `main`).
  - Item 003 (loader exposing `Case.label_inventory`, the raw inventory this
    summariser consumes) — **complete** (on `main`).
- **Not a dependency:** Item 005 (heuristic-config file loader). This item ships an
  in-code default + in-memory override only; the on-disk config schema is item
  005's concern (see *Config override without item 005*).
- **Downstream (this item unblocks):**
  - Item 006 (CLI `run` prints the label inventory **with anatomical names** via
    this module — closes a Stage 0 acceptance criterion).
  - Stage 2 feature extraction (level-aware centroids, ordering) keys off the
    name↔value↔ordinal convention.
  - Stage 4 heuristics ("missing levels", sequence continuity) consume the
    canonical ordered sequence.

---

## Decisions & Trade-offs

Open implementation choices for this item, with recommendations. **Final
decisions recorded below** (executed 2026-06-25).

1. **Type shape — frozen `@dataclass` `LabelConvention` vs a bare dict + module
   functions.** ✅ **Frozen `@dataclass` `LabelConvention`** holding the
   authoritative `value_to_name` plus a precomputed reverse map (`_name_to_value`,
   keyed by the *normalised* name). Immutable, carries its override, mirrors
   `io.py`'s dataclass style. `LabelConvention.default()` returns the shipped
   default; `from_mapping(...)` builds a custom one. The reverse map is built once
   at construction in `from_mapping`. Both `value_to_name` and `_name_to_value`
   are stored as `types.MappingProxyType` over private `dict` copies, so lookups
   are O(1) and external mutation can't leak in — `frozen=True` only blocks
   rebinding the attribute, so without the read-only proxy
   `conv.value_to_name[1] = "HACKED"` would have corrupted a "frozen" instance in
   place (closed by validator test `test_convention_is_immutable_no_dict_leak`).
2. **Exact default TotalSegmentator/VerSe integer↔name table** — ✅ pinned in
   `DEFAULT_LABEL_MAP`. Final table: C1–C7 = **1–7**, T1–T12 = **8–19**,
   L1–L5 = **20–24**, sacrum `S` = **25**, coccyx `Cocygis` = **26**, and the two
   transitional vertebrae at the high end — **T13 = 28**, **L6 = 29** (value `27`
   is intentionally left unmapped, matching the gap in the TotalSegmentator/VerSe
   numbering). Integer order therefore does **not** equal anatomical order (T13 is
   value 28 but sits between T12 and L1); `CANONICAL_ORDER` is the source of truth
   for ordering, and a test asserts `T12 < T13 < L1` and `L5 < L6 < S` in that
   tuple. The default is asserted to be a bijection (unique values, unique names).
3. **`value_of` on unknown name — return `None` vs raise.** ✅ **Return `None`**,
   for symmetry with `name_of`'s `UNKNOWN` sentinel — both lookups are total and
   non-throwing. Raising is reserved for *programmer* errors (a malformed
   override), not *data* questions about a missing name.
4. **Unknown-value outcome — sentinel string `UNKNOWN` vs `None`.** ✅ Module
   constant **`UNKNOWN = "unknown"`** so `name_of` always returns a `str` (simpler
   for CLI/report formatting in item 006), with `is_known()` as the boolean test.
5. **Override semantics — replace vs layer-over-default.** ✅ **`from_mapping`
   replaces** — the user mapping is fully authoritative (default values no longer
   resolve under an override). No `base=`/layering parameter was added; no test
   motivated it, and a clean replace is least surprising for "use my segmenter's
   numbering". (Layering remains an easy future addition if needed.)
6. **Exception type — new `LabelConventionError` vs reuse `io.SegQCInputError`.**
   ✅ **Reuse `segqc.io.SegQCInputError`** so callers (the CLI in item 006) catch
   one input-error type for both load and label-convention problems. Raised on a
   duplicate name in an override and on a non-integer key. The non-integer-key
   check is **strict** (`isinstance(raw_value, int)` excluding `bool`) rather than
   `int(raw_value)`: coercion would parse string keys (`"5"` → 5) and truncate
   float keys (`2.5` → 2), silently corrupting the label map and even collapsing
   `{2: …, 2.5: …}` into one entry without error. Loud rejection keeps label maps
   integer (vision §4) and is covered by validator tests
   `test_override_non_integral_float_key_raises`,
   `test_override_string_integer_key_raises`, and
   `test_override_float_key_cannot_silently_collide`. Relatedly, `value_of` keeps
   its total, non-throwing contract for a non-`str` argument too: `value_of(None)`
   returns `None` instead of leaking an `AttributeError` from `.strip()` (validator
   test `test_value_of_none_does_not_leak_attributeerror`).
7. **Name normalisation — case-insensitive, whitespace-stripped.** ✅ Canonical
   names are stored **verbatim** (`"C1"`, `"T12"`, `"S"`, `"Cocygis"`); lookup
   keys are normalised with `strip().upper()`, so `" l1 "` and `"c1"` resolve.
   Duplicate-name detection runs on the *normalised* key, so `"C1"` and `"c1"` in
   one override collide (tested). Sacrum is spelled **`"S"`**; the coccyx entry is
   **`"Cocygis"`** (matching the TotalSegmentator label name).
8. **Summariser input — plain `{label: count}` only vs also accept a `Case`.** ✅
   **Plain `Mapping[int, int]` only.** This keeps `labels.py` free of any
   `Case`/NIfTI dependency at the summariser boundary — the loader already exposes
   `Case.label_inventory` as exactly this shape, so a caller passes
   `summarise_inventory(case.label_inventory)` (covered by an integration test
   that round-trips through `load_case`). `labels.py` imports only
   `SegQCInputError` from `segqc.io` (a cheap exception class), so the import stays
   light. No `Case` convenience overload was added.

### Implementation notes

- New file `src/segqc/labels.py`; tests in `tests/test_labels.py` (no edits to
  `io.py` or `cli.py`). The summariser orders unknown labels by ascending value
  and recognised labels by `CANONICAL_ORDER` (custom-override names not in the
  canonical tuple sort after the canonical ones, then by name — so a custom
  convention never crashes the summariser).
- `InventorySummary` exposes `recognised` (`(value, name, count)` triples) and
  `unknown` (`(value, count)` pairs) plus convenience properties `n_recognised`,
  `n_unknown`, and `present_levels`.

### Known follow-up

- When item 005 (heuristic-config loader) lands, allow the versioned config to
  *carry* a label-map override and hand it to `LabelConvention.from_mapping`. The
  on-disk schema is item 005's; this item only needs the in-memory hook.

---

## Testing Prerequisites

### Required Services

**None.** This item is a self-contained, pure-Python module operating on in-memory
mappings. No databases, APIs, message queues, or other external services. (Row
included per the work-item template; services first appear in Stage 9 XNAT/Docker
work.)

### Environment Configuration

- **Python:** 3.9 or newer on `PATH`.
- **Virtual environment:** clean venv recommended (`python -m venv .venv`, then
  activate).
  - Windows (PowerShell): `.\.venv\Scripts\Activate.ps1`
  - macOS/Linux: `source .venv/bin/activate`
- **Install:** `pip install -e .[dev]` (NumPy + NiBabel + pytest; no new deps).
- **Environment variables / secrets:** none.
- **Configuration files:** none authored by this item (override is in-memory).
- **Ports:** none.
- **Test data:** the item 002 synthetic fixtures + inline mappings; nothing
  committed, nothing downloaded.

### Manual Validation Checklist

- [ ] **Build succeeds:** `pip install -e .[dev]` completes on Python 3.9+.
- [ ] **Tests pass:** `pytest` (or `python -m pytest`) is green, including the new
      `tests/test_labels.py`.
- [ ] **Services started:** N/A — no services.
- [ ] **Application runs:** `python -c "import segqc.labels"` imports cleanly (and
      `segqc --help` still exits `0`, unaffected by this item).
- [ ] **Feature verified:** in a REPL, `LabelConvention.default().name_of(1)`
      returns the cervical-start name (e.g. `"C1"`), `value_of("L1")` returns its
      integer, an unmapped integer returns `UNKNOWN`, and
      `summarise_inventory(case.label_inventory)` over a fixture splits recognised
      vs unknown correctly.
- [ ] **Data verified:** the default map round-trips (bijection) and the
      transitional vertebrae (T13, L6, S) are present and anatomically ordered.
- [ ] **Health checks pass:** N/A — no server/health endpoint.

### Expected Outcomes

- `import segqc.labels` succeeds; `LabelConvention`, the default factory, and
  `summarise_inventory` are importable and type-hinted.
- The default mapping is a bijection covering C1–C7, T1–T13, L1–L6, S; both
  lookup directions invert for every entry.
- A custom override replaces the default and is reflected in both directions.
- Unknown / out-of-range / negative labels yield `UNKNOWN` (value→name) and are
  collected into the summary's `unknown` list — never dropped, never crashing.
- `summarise_inventory` over the `labelled_blocks` fixture lists the present
  vertebrae with names + counts in anatomical order; over the `empty_labelmap`
  fixture it returns empty recognised/unknown collections.
- `pytest` reports `tests/test_labels.py` passing with `0` failures.

---

## Validation Results

Executed 2026-06-25 on **Windows 11** (builder implementation; final sign-off and
merge performed by a separate validator per `CLAUDE.md`).

- [x] Service started: N/A (no services)
- [x] Application started successfully: `import segqc.labels` clean; `segqc --help`
      still exits `0` (unaffected by this item)
- [x] Database tables verified: N/A
- [x] Seed data verified: N/A
- [x] API endpoints verified: N/A
- [x] Screenshots captured: N/A (no UI)
- [x] `pip install -e .[dev]`: package already installed editable; `segqc.labels`
      imports with no new dependency
- [x] `pytest` green: **64 passed in 0.47s** (new `tests/test_labels.py` plus the
      existing item 001–003 suites)
- [x] Verified on OS: **Windows 11**, Python 3.11. The module is pure-Python
      (stdlib + typing; only a `SegQCInputError` import from `segqc.io`), with no
      platform-specific code — macOS/Linux behaviour is identical.

REPL feature/data check: `LabelConvention.default().name_of(1) == "C1"`,
`value_of("L1") == 20`, `name_of(9999) == "unknown"`;
`summarise_inventory({1:64,2:64,3:64,999:5})` → `recognised == [(1,'C1',64),
(2,'C2',64),(3,'C3',64)]`, `unknown == [(999,5)]`, `present_levels ==
['C1','C2','C3']`.

---

## Completion Reminder

When this item is complete, update [`../progress.md`](../progress.md):

- Flip the Stage 0 **"Label-convention module: integer label ↔ anatomical
  vertebra, configurable, with a default TotalSegmentator/VerSe mapping"**
  deliverable from 📋 → ✅ (mark it 🚧 while in progress).
- Do **not** tick the Stage 0 *Acceptance* checkboxes that also depend on Items
  006 (the `segqc run` end-to-end inventory print + stub JSON) — that closes with
  item 006. The "Unit tests for loader and label mapping pass" acceptance line is
  partially advanced here (label-mapping half); leave the box for whoever closes
  both halves, or tick only when both loader and label tests are on `main`.
- Per `CLAUDE.md`: work on branch `aide/004-label-convention` (push it **before**
  real work to claim the item), `git pull --rebase` before editing
  `progress.md`, and keep the edit scoped to this item's row. A work item may
  merge **straight to `main` once green — no PR required** (here, a separate
  validator performs the merge).

---

## Next Step

Start a **new chat session** and run `/speckit-aide-execute-item 004` to
implement this work item.