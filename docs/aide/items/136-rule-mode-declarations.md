# Item 136 — Declare each rule's targeted §6 failure modes at the rule layer

> **Created:** 2026-09-02 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 20 — Failure-Mode ↔ Feature ↔ Rule Traceability & Specificity Harness
> **Queue:** [`../queue/queue-019.md`](../queue/queue-019.md) · Item 136
> **Objectives:** G2 (every failure mode has a detector, stated not implied), G7 (honest reporting of what is and is not established)
> **Suggested branch:** `aide/136-declare-each-rule-s-targeted`

---

## Description

Give the `rule_id → §6 failure mode` relationship a place to be **stated**.
Today it can only be **inferred**: `segfacet.catalogue._scan_synth_rule_mode_map`
AST-scans `src/segfacet/synth/*.py` for `Expectation(failure_mode=N, …,
expected_rule_ids=frozenset({…}))` literal pairs, so a rule is attributed to a
mode **only when a corpus case designates it for that mode**. The consequence is
structural, not incidental:

- the four rules Stage 20 must disposition (`bounds`, `intensity`,
  `reference_delta`, `intensity_reference_delta`) are mode-less *by
  construction*, whatever the truth about them — no judgement about them can be
  recorded through the existing mechanism at all;
- the matrix's **rule → mode** direction, one of the two roadmap Stage 20
  requires to be complete, has nowhere to live.

This item adds the missing seam, **owned by the rule layer**: a
`RuleModeDeclaration` carried as a class attribute on each concrete `Rule`,
stating either the §6 mode(s) the rule targets (with the evidence behind them),
or that it targets none (with the reason), or that its disposition is deferred
(with the carrier named). The corpus-derived map becomes *corroborating
evidence* rather than the source of truth, and disagreement between the two is a
test failure in **both** directions — a declared mode no corpus case supports,
and a corpus case designating a rule for a mode the rule does not declare.
`catalogue.py`'s `failure_modes` / `mode_evidence` derivation gains the
declaration as a **third source**, alongside `per_mode_metric` and
`rule_mode_map`.

**Populated here for the six corroborated rules only** — `border`→6,
`coverage`→5, `fragmentation`→2,3, `mislabel`→1,4, `overlap`→8, `sequence`→7.
The four contested rules get an explicit **pending** declaration naming item 137
as their carrier: they must not be silent (Stage 20 forbids a silent row) and
must not be pre-empted (their disposition is item 137's judgement, not this
item's).

**What this item is NOT.** It is not the traceability matrix (item 138), not the
exercise report (item 139), not the specificity ratchet (item 140), and it
dispositions nothing. It changes no threshold, no extractor, no rule
verdict, no report schema and no CLI behaviour: the declaration is metadata read
by the catalogue and by tests, never by `evaluate`. It does not edit
`vision.md` or `roadmap.md`.

**Expected artifact movement** (measured on the committed catalogue,
2026-09-02): of 138 entries, 32 carry `mode_evidence` containing
`"rule_mode_map"` and will gain `"rule_declaration"` beside it; 18 stay
`("rule_unmapped",)`; 86 stay empty; 2 stay `("per_mode_metric",)`. **No
entry's `failure_modes` changes**, because the six declarations equal the
corpus-derived map exactly and the four pending declarations contribute no
modes. `docs/aide/feature_catalogue.generated.json` is therefore regenerated;
`feature_catalogue.generated.md` does not render `mode_evidence` and is expected to come back byte-identical.

## Acceptance Criteria

- [ ] **AC1: The declaration type exists and is exported.**
  `segfacet.heuristics.rule.RuleModeDeclaration` is a frozen dataclass with the
  fields `modes: Tuple[int, ...]`, `evidence: Tuple[str, ...]`,
  `mode_less_reason: str` and `pending_reason: str`, each defaulting to empty,
  and it is re-exported from `segfacet.heuristics` (present in that package's
  `__all__`).

- [ ] **AC2: A silent or malformed declaration cannot be constructed.**
  `RuleModeDeclaration(...)` raises `ValueError` for every ill-formed shape: all
  four fields empty; more than one of {non-empty `modes`, non-empty
  `mode_less_reason`, non-empty `pending_reason`} realised at once; non-empty
  `modes` with empty `evidence`; `modes` not strictly ascending; `modes`
  carrying a duplicate, a value `< 1`, or a non-`int`; any `evidence` element
  that is not a non-empty `str`. Each message names the offending field.

- [ ] **AC3: The seam is total over the shipped registry.** After importing
  `segfacet.heuristics`, every rule yielded by `iter_rules()` has a
  `mode_declaration` attribute that is a `RuleModeDeclaration` instance — ten
  rules, none `None`, none inheriting the `Rule` base default.

- [ ] **AC4: The six corroborated rules declare exactly the corpus-designated
  modes.** `border` declares `(6,)`, `coverage` `(5,)`, `fragmentation`
  `(2, 3)`, `mislabel` `(1, 4)`, `overlap` `(8,)`, `sequence` `(7,)`; each
  carries `"corpus"` among its `evidence` tags and has empty
  `mode_less_reason` and `pending_reason`.

- [ ] **AC5: The four contested rules are pending, not pre-empted.** `bounds`,
  `intensity`, `reference_delta` and `intensity_reference_delta` each declare
  `modes == ()`, `mode_less_reason == ""`, and a non-empty `pending_reason`
  whose text contains `137`.

- [ ] **AC6: Declarations and the corpus-derived map agree on this tree.**
  `segfacet.catalogue.rule_declaration_conflicts()` returns an empty tuple, and
  for every `(rule_id, mode)` pair in
  `segfacet.catalogue.scan_synth_rule_mode_map()`, `mode` is present in that
  rule's declared `modes`.

- [ ] **AC7: A corpus-designated mode a rule fails to declare is reported,
  naming both.** With one registered rule's `mode_declaration` replaced by a
  declaration that drops a mode the corpus designates for it,
  `rule_declaration_conflicts()` returns at least one message containing that
  `rule_id` and the decimal form of the dropped mode number.

- [ ] **AC8: A declared mode no corpus case supports is reported, naming both.**
  With one `"corpus"`-tagged declaration replaced by one that adds a mode no
  `Expectation(...)` designates for that rule,
  `rule_declaration_conflicts()` returns at least one message containing that
  `rule_id` and the decimal form of the surplus mode number.

- [ ] **AC9: A registered rule with no declaration registers without error and
  is reported by the checker.** `register_rule` accepts a `Rule` subclass that
  sets no `mode_declaration` (no exception raised),
  `segfacet.heuristics.rule.declaration_for` returns `None` for it, and
  `rule_declaration_conflicts()` returns at least one message containing that
  rule's `rule_id`.

- [ ] **AC10: This item moves no attribution.** For every registered rule, its
  declared `modes` is a subset of `scan_synth_rule_mode_map().get(rule_id, ())`
  — the declaration source adds a statement, never a new mode.

- [ ] **AC11: The catalogue gains the declaration as a third evidence source.**
  In a fresh `build_catalogue(strict=True)`, an entry's `mode_evidence`
  contains `"rule_declaration"` if and only if at least one of its
  `consuming_rules` carries a declaration with non-empty `modes`; where present
  the tag is last, after any `"per_mode_metric"` and `"rule_mode_map"`.

- [ ] **AC12: The `failure_modes` column is unchanged by the new source.** For
  every entry of a fresh `build_catalogue(strict=True)`, `failure_modes` equals
  `tuple(sorted(anchor_modes ∪ corpus_rule_modes))`, recomputed independently in
  the test from `segfacet.feature_docs.MODE_ANCHOR_PATHS` and
  `scan_synth_rule_mode_map()` over the entry's `consuming_rules`.

- [ ] **AC13: Both committed catalogue artifacts regenerate byte-identically.**
  `segfacet.catalogue.main(["--json", <tmp>, "--md", <tmp>])` writes files
  byte-equal to the committed `docs/aide/feature_catalogue.generated.json` and
  `feature_catalogue.generated.md`, and the JSON's `schema_version` is still `"1.1"`.

- [ ] **AC14: The seam is metadata only.** Replacing a registered rule's
  `mode_declaration` (with any well-formed declaration) leaves
  `segfacet.heuristics.run_rules(record, config)` returning an equal list of
  `Finding`s for a fixed fixture record — no rule reads its own declaration
  during `evaluate`.

## Assumptions

- **A1 (seam shape):** the declaration is a frozen dataclass held as the class
  attribute `mode_declaration` on each concrete `Rule` subclass, in that rule's
  own module — not a central table. The queue asks for a seam "owned by the rule
  layer", and `tests/test_103_feature_catalogue.py::test_ac13_no_hand_typed_rule_mode_dict_in_catalogue_source`
  independently forbids a hand-typed rule-id → mode dict literal inside
  `catalogue.py`, so a central table there is not available anyway.
- **A2 (three states, `pending` included):** a third `pending` state exists so
  all ten rules carry a declaration in this item without pre-empting item 137.
  It is deliberately distinct from *absent*: a forgotten declaration and a
  deliberately deferred one must not look alike, since Stage 20's rule is that a
  silent row is the only unacceptable outcome. **This pins the interface item
  137 consumes:** item 137 replaces each of the four `pending` declarations with
  either non-empty `modes` + `evidence`, or a non-empty `mode_less_reason`.
- **A3 (no hard gate at registration):** `register_rule` does **not** reject an
  undeclared rule; `Rule.mode_declaration` defaults to `None` on the ABC and
  completeness is enforced by `rule_declaration_conflicts()` and by tests over
  the shipped registry. Two reasons: items 138 and 139 must be able to register
  a dummy rule with no declaration to prove their own completeness checks fail
  loudly, which a registration-time raise would make untestable; and the eight
  existing stub `Rule` subclasses in `tests/test_026_rule_engine_core.py` and
  `tests/test_103_feature_catalogue.py` register without one today.
- **A4 (evidence is per-declaration, and `"corpus"` is reserved):** `evidence`
  is a tuple of free-form non-empty strings attached to the declaration as a
  whole, not per mode. The single reserved tag `"corpus"` means "≥1 committed
  corpus case designates this rule for these modes" and is what the
  declaration → corpus direction (AC8) keys on: a declaration **without** that
  tag is bound only by the corpus → declaration direction (AC7), which is what
  lets item 137 declare a mode on analytic grounds without a corpus case.
- **A5 (the in-code §6 mode catalogue):** the eight §6 modes are taken from
  `segfacet.feature_docs.MODE_ANCHOR_PATHS`'s key set — pinned to `{1..8}` by
  `test_103_feature_catalogue.py::test_ac14_mode_anchor_paths_key_set_is_one_to_eight`
  — rather than a second hardcoded mode list. `rule_declaration_conflicts()`
  reports a declared mode outside that key set; `RuleModeDeclaration` itself
  validates only structural well-formedness (`int`, `>= 1`, strictly ascending),
  so the rule layer does not import `feature_docs`.
- **A6 (checker placement):** `rule_declaration_conflicts()` and the public
  `scan_synth_rule_mode_map()` live in `segfacet.catalogue`, which already owns
  the derived map and already imports `iter_rules`. The rule layer must not
  import `catalogue` (cycle + import cost), so the comparison cannot live in
  `rule.py`.
- **A7 (artifact regeneration):** the committed
  `docs/aide/feature_catalogue.generated.json` is regenerated in this item
  because `mode_evidence` gains a value on 32 of its 138 entries (measured
  2026-09-02). `failure_modes`, `status`, `consuming_rules`, `rule_evidence`,
  `consumers`, `observed` and `schema_version` must not move; `feature_catalogue.generated.md` does not
  render `mode_evidence` and is expected to regenerate byte-unchanged.
- **A8 (no behaviour change):** declarations are inert at evaluation time.
  `Rule.evaluate`'s signature, `run_rules`, `report_schema_v0.json`, every
  verdict and every finding are unchanged (AC14 is the test of this).
- **A9 (engine 1.37.0):** `aide check`'s `.gitattributes` lint needs nothing new
  — both catalogue artifacts are already pinned `text eol=lf`
  (`.gitattributes` lines 40–41) and this item commits no new byte-reproducible
  fixture.

## Implementation Steps

1. **`src/segfacet/heuristics/rule.py`** — add the declaration seam:
   - `@dataclass(frozen=True) class RuleModeDeclaration` with the four fields of
     AC1 and a `__post_init__` implementing AC2's validation (exactly one state;
     modes require evidence; modes strictly ascending, unique, `int`, `>= 1`;
     evidence elements non-empty `str`). Add a convenience constructor or
     documented usage for each of the three states in the class docstring.
   - `Rule.mode_declaration: Optional[RuleModeDeclaration] = None` as an ABC
     class attribute, documented as "every concrete rule must set this".
   - `declaration_for(rule_or_id) -> Optional[RuleModeDeclaration]` and
     `iter_rule_declarations() -> Iterator[Tuple[str, Optional[RuleModeDeclaration]]]`
     (ascending `rule_id`), both added to `__all__`.
   - Leave `register_rule`'s validation untouched (A3).
2. **The six corroborated rule modules** — `border.py` (6), `coverage.py` (5),
   `fragmentation.py` (2, 3), `mislabel.py` (1, 4), `overlap.py` (8),
   `sequence.py` (7): set `mode_declaration = RuleModeDeclaration(modes=…,
   evidence=("corpus",))` on the concrete rule class, with a short comment
   naming the corpus case(s) that designate it. Extend each module docstring
   with one line stating the targeted mode(s).
3. **The four contested rule modules** — `bounds.py`, `intensity.py`,
   `reference_delta.py`, `intensity_reference_delta.py`: set
   `mode_declaration = RuleModeDeclaration(pending_reason="…")` whose text names
   **item 137** as the carrier and states, in one sentence, why the disposition
   is not derivable here (no corpus case designates the rule, so the existing
   mechanism attributes it to nothing by construction). Do **not** guess a mode.
4. **`src/segfacet/heuristics/__init__.py`** — re-export
   `RuleModeDeclaration`, `declaration_for`, `iter_rule_declarations`; extend
   the package docstring's Public API list.
5. **`src/segfacet/catalogue.py`**:
   - expose `scan_synth_rule_mode_map()` as the public name for the existing
     `_scan_synth_rule_mode_map()` (keep the private name as an alias if
     internal callers read better that way — no dict literal keyed by rule ids
     may appear in this module, see A1);
   - in `build_catalogue`, collect `declared_modes_by_rule` from
     `iter_rule_declarations()`, union declared modes into `all_modes`, append
     `"rule_declaration"` to `mode_evidence_parts` **last** when a declaration
     contributed, and treat a rule as unmapped (`had_unmapped_rule`) only when
     it has neither corpus-derived nor declared modes;
   - add `rule_declaration_conflicts() -> Tuple[str, ...]`, returning sorted
     human-readable messages for: a registered rule with no declaration
     (naming the `rule_id`); a corpus-designated `(rule_id, mode)` absent from
     the declaration (naming both); a `"corpus"`-tagged declaration carrying a
     mode the corpus does not designate (naming both); a declared mode outside
     `MODE_ANCHOR_PATHS`'s key set (naming both). Empty tuple means agreement.
   - update the module docstring's "Four derivation mechanisms" section to
     record the declaration as a source of `failure_modes` / `mode_evidence`.
6. **Regenerate the committed catalogue**: `.venv/bin/python -m segfacet.catalogue`,
   then confirm by `git diff` that only `mode_evidence` lists moved in the JSON
   and that the `.md` is unchanged.

## Authorised paths

**May change:**

- `src/segfacet/heuristics/rule.py` — the declaration type, the ABC attribute, the accessors (AC1–AC3, AC9).
- `src/segfacet/heuristics/__init__.py` — re-export the new public names (AC1).
- `src/segfacet/heuristics/border.py` — declares mode 6 (AC4).
- `src/segfacet/heuristics/coverage.py` — declares mode 5 (AC4).
- `src/segfacet/heuristics/fragmentation.py` — declares modes 2, 3 (AC4).
- `src/segfacet/heuristics/mislabel.py` — declares modes 1, 4 (AC4).
- `src/segfacet/heuristics/overlap.py` — declares mode 8 (AC4).
- `src/segfacet/heuristics/sequence.py` — declares mode 7 (AC4).
- `src/segfacet/heuristics/bounds.py` — pending declaration naming item 137 (AC5).
- `src/segfacet/heuristics/intensity.py` — pending declaration naming item 137 (AC5).
- `src/segfacet/heuristics/reference_delta.py` — pending declaration naming item 137 (AC5).
- `src/segfacet/heuristics/intensity_reference_delta.py` — pending declaration naming item 137 (AC5).
- `src/segfacet/catalogue.py` — public map scan, the declaration source, `rule_declaration_conflicts()` (AC6–AC12).
- `docs/aide/feature_catalogue.generated.json` — regenerated; `mode_evidence` gains `"rule_declaration"` on 32 of 138 entries (AC11, AC13).
- `docs/aide/feature_catalogue.generated.md` — written by the same regeneration command; expected byte-unchanged (AC13).
- `tests/test_136_rule_mode_declarations.py` — this item's test module.

**Asserts against:**

- `src/segfacet/synth/*.py` — the `Expectation(failure_mode=…, expected_rule_ids=…)` literals AC6–AC8, AC10 and AC12 read through the AST scan; this item designates no new corpus case and changes none.
- `src/segfacet/feature_docs.py` — `MODE_ANCHOR_PATHS`, the in-code §6 mode catalogue AC12 recomputes anchor modes from and A5 validates against; read only.
- `tests/committed_artifact_guard.py` — the `ALLOWLIST` entry that makes AC13's byte-exact fresh-vs-committed comparison legitimate; read only, no new entry needed.

## Testing Strategy

New module: **`tests/test_136_rule_mode_declarations.py`**, one focused test per
AC, plus:

- **Adversarial construction table (AC2)** — parametrised over: all fields
  empty; `modes` + `mode_less_reason`; `modes` + `pending_reason`;
  `mode_less_reason` + `pending_reason`; `modes` with empty `evidence`;
  `modes=(2, 1)`; `modes=(2, 2)`; `modes=(0,)`; `modes=(-1,)`;
  `modes=(True,)` / `modes=("2",)`; `evidence=("",)`. Each asserts `ValueError`
  and that the message names the offending field.
- **Registry isolation** — every test that registers a stub rule snapshots and
  restores `segfacet.heuristics.rule._RULES` (the house pattern in
  `tests/test_026_rule_engine_core.py`), so AC9's undeclared stub cannot leak
  into AC6's clean-tree assertion.
- **Both failure directions are driven, not asserted by inspection** (AC7, AC8)
  — monkeypatch one registered rule's `mode_declaration`, call
  `rule_declaration_conflicts()`, restore. Assert on message *content*
  (`rule_id` and the mode's decimal form), never on message identity or
  ordering position.
- **Determinism / immutability** — `rule_declaration_conflicts()` called twice
  in one session returns equal tuples; `build_catalogue()` called twice returns
  equal `mode_evidence` for every path; no declaration object is mutated by any
  check (frozen dataclass, asserted by an attempted attribute set raising).
- **Edge cases** — a declaration whose `evidence` contains `"corpus"` plus
  another tag still binds AC8; a rule whose `consuming_rules` is empty gains no
  `"rule_declaration"` tag (AC11's "only if" half); an entry attributed only via
  `per_mode_metric` keeps `("per_mode_metric",)` unchanged.
- **Portability** — no absolute path literals; the committed artifacts are
  addressed from `Path(__file__).resolve().parent.parent`; regeneration writes
  into `tmp_path`, never over the committed copies.

**Existing tests to reconcile** (all must stay green — none is expected to
need editing, but each is a live tripwire for a wrong implementation):

- `tests/test_103_feature_catalogue.py::test_ac13_no_hand_typed_rule_mode_dict_in_catalogue_source`
  — fails if the declarations are implemented as a dict literal in
  `catalogue.py` keyed by the six rule ids. They must live in the rule modules.
- `tests/test_103_feature_catalogue.py::test_ac15_unmapped_rule_only_entry_is_honestly_unmapped`
  — asserts `mode_evidence == ("rule_unmapped",)` for entries consumed only by
  the four contested rules. It stays green **because** those four are `pending`
  and contribute no modes (AC5); if it goes red, the item has pre-empted item
  137. (It is item **137**'s to update, not this item's.)
- `tests/test_103_feature_catalogue.py::test_ac14_every_anchor_path_present_with_per_mode_metric_evidence`
  — `"per_mode_metric" in mode_evidence` must survive appending a third tag.
- `tests/test_026_rule_engine_core.py` — seven stub `Rule` subclasses register
  with no declaration; they prove A3's non-enforcement is real.
- `tests/test_120_leave_one_out_offset.py`, `tests/test_131_tangent_direction_normalisation.py`,
  `tests/test_132_monotonicity_against_traversal_order.py` — each carries a
  byte-exact fresh-vs-committed catalogue comparison; all three go red until the
  committed JSON is regenerated (step 6), and green afterwards.
- `tests/test_111_golden_guard.py`, `tests/test_105_golden_decision_table.py` —
  both name the catalogue artifacts by path only (no hashes); regeneration does
  not disturb them.

## Validation

Beyond the suite, observe the seam and the artifact movement directly (no
`[validation]` profile needed — CPU-only, no optional dependency):

1. `.venv/bin/python -m segfacet.catalogue` — regenerates both artifacts in place.
2. `git diff --stat docs/aide/feature_catalogue.generated.json docs/aide/feature_catalogue.generated.md`
   — expect the JSON changed and the `.md` untouched.
3. `git diff -U0 docs/aide/feature_catalogue.generated.json | grep -c rule_declaration`
   — expect 32 added lines carrying the new tag, and **no** line whose diff
   context is `"failure_modes"`.
4. `.venv/bin/python -c "print(__import__('segfacet.catalogue', fromlist=['x']).rule_declaration_conflicts())"`
   — expect `()`.
5. `.venv/bin/python -c "print([(r.rule_id, r.mode_declaration) for r in __import__('segfacet.heuristics', fromlist=['x']).iter_rules()])"`
   — the ten-rule roll call: six with modes and `("corpus",)`, four `pending`
   naming item 137. Read it as the human-legible form of AC3–AC5.

## Dependencies

None. This item opens queue-019's critical path and depends on nothing
unlanded.

**Downstream:** item 137 fills the four `pending` declarations this item
creates and **must list `tests/test_136_rule_mode_declarations.py` under its own
May-change paths** — its AC5 (four rules pending), AC10 (declared ⊆ corpus) and
AC12 (`failure_modes` recomputed without the declaration source) are premises
about the pre-137 state and become false by design when 137 lands. Items 138
(traceability matrix), 139 (exercise report) and 142 (stage validation) read the
declarations and `rule_declaration_conflicts()` this item introduces; item 138's
"a deliberately un-declared rule fails the rule → mode direction loudly" is
served by AC9's non-enforcing `register_rule`.

## Decisions & Trade-offs

- **Field-name mapping for AC2 messages**: each `__post_init__` branch's
  `ValueError` message spells the exact dataclass field name it violates
  (`'modes'`, `'evidence'`, `'mode_less_reason'`, `'pending_reason'`) so the
  test's `any(name in message for name in expected_field_names)` check binds
  regardless of which offending field the test parametrises on. The
  multi-state check (`all_four_empty`, the three pairwise combinations) names
  all candidate fields in one message rather than picking one, since more
  than one field is genuinely implicated.
- **Duplicate check runs before the ascending check**: `modes=(2, 2)` fails
  the `len(set(...)) != len(...)` duplicate test before it would reach the
  `sorted(...) != list(...)` ascending test (which a duplicate value alone
  would not necessarily fail, e.g. `(2, 2)` is technically "sorted"). This
  keeps the two AC2 rows (`modes_duplicate`, `modes_not_ascending`) reporting
  on the field they are testing rather than always landing on the same
  message.
- **`declared_modes_by_rule` union is safe for AC12 because AC10 holds**: the
  catalogue's `all_modes` now unions `anchor_modes | mapped_rule_modes |
  declared_rule_modes`. AC12 requires `failure_modes` to equal
  `anchor_modes ∪ corpus_rule_modes` alone (recomputed independently, with no
  declaration term) — this only holds because every declared mode on this
  tree is already a member of the corpus-derived map (AC10, enforced by
  `rule_declaration_conflicts()`). Item 137, which is explicitly allowed to
  declare a mode with no corpus case (A4), will need to keep this invariant
  in mind: an analytic-only declared mode would need `failure_modes` (item
  138's traceability matrix territory, per the item 136 spec's "What this
  item is NOT") reconsidered, not this item's `build_catalogue` union as
  written — but on this tree the union changes nothing (`declared ⊆ corpus`
  everywhere, verified by AC10's own test).
- **`had_unmapped_rule`** now fires only when a `consuming_rules` entry has
  *neither* a corpus-derived nor a declared mode — this matches the spec's
  Implementation Steps wording exactly and, since the four contested rules'
  declarations are `pending` (empty `modes`), it leaves
  `test_ac15_unmapped_rule_only_entry_is_honestly_unmapped` untouched (their
  `mode_evidence` still lands on `("rule_unmapped",)`).
- **`rule_declaration_conflicts()` message text is free-form**, not a stable
  format string — AC7-AC9 only assert on substring presence (`rule_id` and a
  mode's decimal form), matching the Testing Strategy's explicit "assert on
  message content, never on message identity or ordering position."
- **Regeneration measured**: `python -m segfacet.catalogue` moved exactly 32
  `mode_evidence` entries (all gaining `"rule_declaration"` as the last
  element), 0 `failure_modes` lines, and left
  `feature_catalogue.generated.md` byte-unchanged — matching the item's
  "Expected artifact movement" section exactly.
