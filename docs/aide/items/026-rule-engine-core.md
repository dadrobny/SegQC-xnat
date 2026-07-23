# Item 026 — Rule-Engine Core: `Rule` Abstraction, Finding Model & Config-Driven Runner

> **Created:** 2026-06-29 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 4 — Heuristic Rule Engine over the Failure Modes (G2)
> **Queue:** [`../queue/queue-003.md`](../queue/queue-003.md) · Item 026
> **Objectives:** G2 (explainable rule engine), supporting G4 (per-case reasons)
> **Suggested branch:** `aide/026-rule-engine-core`

---

## Description

Establish the **explainable rule-engine foundation** that every Stage 4 rule
family (items 027–035) plugs into. This item builds **only the engine core** —
the data model, the rule abstraction, the registry, the runner, and the config
plumbing. It deliberately implements **no concrete rule family** (no bounds,
fragmentation, coverage, sequence, border, overlap, or mislabel logic — those
are items 027–033).

Create a new package `src/segqc/heuristics/` containing:

1. **A rule-finding data model** — a frozen `Finding` dataclass carrying:
   - `rule_id` (str): the id of the rule that produced the finding,
   - `severity` (`segqc.verdict.Severity`): reuse the existing Stage 1 severity
     enum (`PASS < FLAG < FAIL`) so findings aggregate cleanly into the QC
     verdict in item 034,
   - `reason` (str): a human-readable, non-empty explanation,
   - `labels` (`frozenset[int]`): the offending vertebra label values (may be
     empty for a case-level finding).
   It supports lossless `to_dict()` / `from_dict()` round-tripping for
   serialisation.

2. **A `Rule` abstraction** — an abstract base class (or equivalent) defining a
   stable contract: a class-level `rule_id` string and an
   `evaluate(record, config) -> list[Finding]` method that inspects the per-case
   feature record and returns zero or more findings. Rules are **stateless**;
   all thresholds are read from `config` at evaluate time.

3. **A registry** — a module-level registry plus a `register_rule` decorator so
   rule families self-register on import, keyed by `rule_id`. Duplicate ids are
   rejected. The registry can be iterated deterministically (sorted by
   `rule_id`).

4. **A config-driven runner** — `run_rules(record, config, rules=None)` that
   selects the enabled rules (from the registry by default, or an explicit list),
   executes them **deterministically** over the feature record, and returns the
   aggregated list of findings. It tolerates an empty rule set and a feature
   record with no labels without crashing, and never mutates its inputs.

5. **An extension of the versioned heuristic-config loader** (`segqc/config.py`)
   so each rule reads its thresholds from a documented per-rule config section
   (rule on/off + parameters), with sensible **built-in defaults supplied by the
   caller** when a key is absent. The change is backward-compatible: existing
   flat fields, `schema_version`, `default_config()`, and `load_config()` keep
   working; a config file with no `rules` section loads cleanly with all rules
   enabled by default.

### The "per-case feature record"

The record the runner and rules consume is the assembled **`features` block
dict** produced by `segqc.feature_report.build_features_block` (a JSON-ready
`Mapping[str, Any]` with `per_label`, `relationships`, `overlaps`, and an
optional `stage3` sub-block). The engine core treats it as an opaque read-only
mapping; concrete rules (027–033) reach into specific sub-keys.

### Scope boundary

| Concern | Owned by |
|---------|----------|
| Finding model, `Rule` ABC, registry, runner, config section | **Item 026 (this item)** |
| `Severity` enum / `Verdict` model | Item 008 (`verdict.py`) — reused, not modified |
| Feature-block assembly (`build_features_block`) | Item 016 (`feature_report.py`) — read, not modified |
| Level-aware bounds rule family | Item 027 |
| Connected-components / fragmentation / island rules | Item 028 |
| Coverage / missing-level rules | Item 029 |
| Label-sequence continuity rule | Item 030 |
| Border-partial rule | Item 031 |
| Overlap rule | Item 032 |
| Mislabel / misalignment rules | Item 033 |
| Verdict aggregation of findings | Item 034 |
| Default shipped config + pipeline/report wiring | Item 035 |

---

## Acceptance Criteria

- [ ] **AC1: `Finding` is a frozen dataclass with the four required fields.**
      `segqc.heuristics.Finding(rule_id="r", severity=Severity.FLAG,
      reason="msg", labels=frozenset({3, 5}))` constructs successfully, is
      frozen (attempting to assign to any field raises
      `dataclasses.FrozenInstanceError`), and exposes `rule_id`, `severity`,
      `reason`, and `labels` with the supplied values.

- [ ] **AC2: `Finding.labels` defaults to an empty frozenset.**
      `Finding(rule_id="r", severity=Severity.PASS, reason="ok")` constructs
      with `labels == frozenset()` (a case-level finding with no label
      attribution).

- [ ] **AC3: A `Finding` requires a non-empty `reason`.**
      Constructing a `Finding` with `reason=""` (or whitespace-only) raises
      `ValueError`. (Explainability: every flag must carry a reason.)

- [ ] **AC4: A `Finding` requires a non-empty `rule_id`.**
      Constructing a `Finding` with `rule_id=""` raises `ValueError`.

- [ ] **AC5: `Finding` round-trips losslessly through `to_dict` / `from_dict`.**
      For any valid finding `f`, `Finding.from_dict(f.to_dict()) == f`. The
      `to_dict()` output is JSON-serialisable (e.g. `severity` is rendered as a
      string label such as `"flagged-for-review"`, and `labels` as a sorted list
      of ints), and contains no raw Python class names or `repr` of enum members.

- [ ] **AC6: `Rule` defines the abstract `evaluate` contract.**
      `segqc.heuristics.Rule` is an abstract base; a subclass that does not
      implement `evaluate` cannot be instantiated, and a subclass that
      implements `evaluate(self, record, config) -> list[Finding]` and sets a
      `rule_id` can be instantiated and called.

- [ ] **AC7: `register_rule` registers a rule under its `rule_id` and it is
      retrievable.**
      Decorating a `Rule` subclass with `@register_rule` places it in the
      registry; the engine exposes a lookup (e.g. `get_rule("stub")`) and a
      deterministic iterator (e.g. `iter_rules()`) that returns the registered
      rule.

- [ ] **AC8: Registering two rules with the same `rule_id` raises.**
      A second `register_rule` of a rule whose `rule_id` already exists raises
      `ValueError` (or a dedicated registry error), preventing silent shadowing.

- [ ] **AC9: The runner executes registered enabled rules and aggregates their
      findings.**
      Given a registered stub rule that emits one known `Finding`,
      `run_rules(record, config)` returns a list containing that finding.

- [ ] **AC10: The runner output is deterministic.**
      Two calls to `run_rules(record, config)` with the same inputs return
      equal lists in the same order; with ≥2 rules registered, findings are
      ordered deterministically (documented order, e.g. ascending `rule_id`,
      then the rule's own emission order).

- [ ] **AC11: The runner tolerates an empty rule set.**
      `run_rules(record, config, rules=[])` returns `[]` and raises nothing.

- [ ] **AC12: The runner tolerates a feature record with no labels.**
      Given a feature record whose `per_label` is empty (and a stub rule that
      reads it), `run_rules(...)` completes without raising and returns a list
      (empty for a stub that emits nothing).

- [ ] **AC13: The runner does not mutate the feature record.**
      The `record` mapping passed to `run_rules` is unchanged (deep-equal to a
      pre-call copy) after the call.

- [ ] **AC14: A rule disabled in config is skipped by the runner.**
      With a config that sets the stub rule's section to `enabled: false`,
      `run_rules(record, config)` returns no findings from that rule; with the
      rule enabled (or absent from config), its findings are included.

- [ ] **AC15: `HeuristicConfig.rule_enabled` defaults to enabled when the rule
      is absent from config.**
      For a `default_config()` (no `rules` section), `cfg.rule_enabled("anything")`
      returns `True`; when the config explicitly sets that rule's
      `enabled: false`, it returns `False`.

- [ ] **AC16: `HeuristicConfig.rule_param` returns the configured value, else the
      caller's built-in default.**
      For a config setting `rules.bounds.params.max_volume_mm3 = 1000`,
      `cfg.rule_param("bounds", "max_volume_mm3", default=42)` returns `1000`;
      for an absent key it returns the supplied `default` (`42`). This is how
      each rule gets "config value if present, else built-in default".

- [ ] **AC17: Config loading is backward-compatible.**
      `default_config()` and `load_config()` still succeed; a YAML config file
      with the supported `schema_version` and **no** `rules` section loads
      without error, yielding a config where every rule is enabled by default.
      A `rules` section in the file is merged in and readable via
      `rule_enabled` / `rule_param`.

- [ ] **AC18: No concrete rule family is shipped in this item.**
      The `segqc/heuristics/` package contains only engine-core modules (finding
      model, rule ABC, registry, runner, and the config extension lives in
      `config.py`); it ships **no** module or class implementing a §6 rule family
      (bounds, fragmentation/island, coverage, sequence, border, overlap, or
      mislabel). Any rule referenced in tests is a local stub defined in the test
      file. (Verified by inspecting the package contents / module list.)

---

## Implementation Steps

1. **Create the package `src/segqc/heuristics/__init__.py`** exporting the public
   API: `Finding`, `Rule`, `register_rule`, `get_rule`, `iter_rules`,
   `run_rules` (and any registry-error type).

2. **`src/segqc/heuristics/finding.py`:**
   - Define `@dataclass(frozen=True) class Finding` with `rule_id: str`,
     `severity: Severity` (imported from `segqc.verdict`), `reason: str`,
     `labels: frozenset = field(default_factory=frozenset)`.
   - In `__post_init__`, validate non-empty `rule_id` and non-empty (stripped)
     `reason`, raising `ValueError` otherwise; coerce `labels` to a `frozenset`
     of ints if a list/iterable is supplied.
   - `to_dict()` → `{"rule_id", "severity": severity.label, "reason",
     "labels": sorted(labels)}`.
   - `from_dict(d)` → reconstruct, mapping the severity label string back to the
     `Severity` member (reuse / add a small label→member lookup).

3. **`src/segqc/heuristics/rule.py`:**
   - Define `class Rule(abc.ABC)` with class attribute `rule_id: str` and
     `@abc.abstractmethod def evaluate(self, record, config) -> list[Finding]`.
   - Define the registry: a module-level dict `_RULES`, a `register_rule`
     class decorator that instantiates (rules are stateless / zero-arg) and
     stores by `rule_id`, raising on duplicate id or missing/empty `rule_id`.
   - `get_rule(rule_id)`, `iter_rules()` (sorted by `rule_id`), and a test
     helper to clear/snapshot the registry (e.g. `_reset_registry()` or a
     context manager) so tests don't leak state.

4. **`src/segqc/heuristics/runner.py`:**
   - `run_rules(record, config, rules=None) -> list[Finding]`:
     - default `rules` to `iter_rules()`;
     - skip any rule where `config.rule_enabled(rule.rule_id)` is `False`;
     - call `rule.evaluate(record, config)` for each enabled rule in
       deterministic order (ascending `rule_id`), extend the result list;
     - never mutate `record`; return the aggregated list.

5. **Extend `src/segqc/config.py`:**
   - Add `"rules": {}` to `_DEFAULTS` and a `rules: Mapping[str, Any] =
     field(default_factory=dict)` field to `HeuristicConfig` (keep the dataclass
     frozen; treat `rules` as read-only).
   - In `load_config`, merge the file's `rules` mapping over the default
     (per-rule), preserving rule ids the loader does not recognise (rules
     self-describe).
   - Add methods to `HeuristicConfig`:
     - `rule_enabled(self, rule_id: str, default: bool = True) -> bool` — reads
       `rules[rule_id]["enabled"]`, else `default`.
     - `rule_params(self, rule_id: str) -> Mapping[str, Any]` — returns
       `rules[rule_id]["params"]` or `{}`.
     - `rule_param(self, rule_id, key, default)` — convenience accessor.
   - Document the `rules` section shape in the module docstring:
     `rules: { <rule_id>: { enabled: bool, params: { <key>: <value> } } }`.

6. **Do NOT** add any concrete rule module. Leave 027–033 to introduce their own
   `*.py` rule modules that import `register_rule` / `Rule` / `Finding`.

7. **Export** the engine-core names from `src/segqc/__init__.py` `__all__` if the
   package convention is to surface top-level API (follow the existing pattern).

---

## Testing Strategy

- **Framework:** `pytest`. Test module: `tests/test_026_rule_engine_core.py`.
- **Registry isolation:** use the registry reset/snapshot helper (or a fixture)
  so each test registers its stub rules into a clean registry and restores state
  afterwards — no cross-test leakage.
- **Stub rules:** define local `Rule` subclasses in the test file (e.g. a
  `StubRule` that always emits one finding, a `ParamRule` that emits a finding
  only when a config param exceeds a threshold, a `LabelCountRule` that reads
  `record["per_label"]`). These exercise the engine without any real §6 logic.
- **Feature record fixtures:** build a minimal `features` block via
  `build_features_block` (or a hand-written dict matching its shape) — one with a
  couple of labels, one with empty `per_label` — to drive AC12/AC13.
- **Coverage map:**
  - AC1–AC4: `Finding` construction, frozenness, field defaults, validation of
    empty `reason` / `rule_id`.
  - AC5: round-trip `to_dict`/`from_dict` for each severity; assert JSON
    serialisability (`json.dumps`) and absence of `repr`/class-name leakage.
  - AC6: abstract `Rule` cannot be instantiated; concrete subclass can.
  - AC7–AC8: register and retrieve; duplicate-id raises.
  - AC9–AC10: runner aggregates stub findings; determinism across two calls;
    multi-rule ordering.
  - AC11: empty rule set → `[]`.
  - AC12: empty-`per_label` record → no crash.
  - AC13: record deep-equal before/after (use `copy.deepcopy` comparison).
  - AC14: disabled-in-config rule skipped; enabled/absent included.
  - AC15: `rule_enabled` default-True and explicit-False.
  - AC16: `rule_param` present vs default fallback.
  - AC17: `default_config()` works; `load_config` on a YAML file without a
    `rules` section loads and reports all rules enabled; with a `rules` section,
    values are readable.
  - AC18: introspect `segqc.heuristics` module/package contents and assert no
    rule-family module/class is present (only finding/rule/runner core).
- **Adversarial / edge cases:**
  - `Finding(labels=[3, 3, 5])` deduplicates to `frozenset({3, 5})`.
  - A rule whose `evaluate` returns `[]` contributes nothing.
  - A config file with a `rules` section but a rule entry missing `params` or
    `enabled` (partial entry) — `rule_param` and `rule_enabled` fall back to
    defaults rather than raising.
  - `from_dict` on an unknown severity label raises a clear error.
  - Running with a record that lacks an expected key (e.g. no `relationships`)
    does not crash the runner itself (individual rules own their own key
    access; the core must not pre-validate record shape).

---

## Dependencies

- **Upstream (all merged ✅):**
  - Item 008 — `segqc.verdict.Severity` (reused as the finding severity enum).
  - Item 005 — `segqc.config` (`HeuristicConfig`, `default_config`,
    `load_config`, `SegQCConfigError`) — extended here.
  - Item 016 — `segqc.feature_report.build_features_block` (defines the
    per-case feature-record shape the runner consumes; read-only).
- **Downstream (gated by this item):**
  - Items 027–033 — each rule family registers a `Rule` and emits `Finding`s
    through this engine.
  - Item 034 — verdict aggregation maps `Finding` severities into the
    `Verdict` model.
  - Item 035 — ships the default `rules` config and wires the runner into the
    pipeline/report.

---

## Decisions & Trade-offs

### Builder decisions (implemented)

1. **`Finding.__post_init__` uses `object.__setattr__` for label coercion.**
   Since `Finding` is `frozen=True`, direct attribute assignment in
   `__post_init__` is forbidden. Labels supplied as a `list` or `set` are
   coerced to `frozenset` via `object.__setattr__(self, "labels", frozenset(...))`,
   the standard pattern for post-construction normalisation in frozen dataclasses.

2. **`register_rule` is a plain function, not a pure decorator.**
   The tests call `register_rule(_StubRule)` rather than using it as a decorator.
   The implementation accepts both forms: it takes the class as an argument,
   instantiates it once, stores the instance, and returns the class unchanged —
   so `@register_rule` and `register_rule(cls)` are both valid.

3. **`_RULES` is a module-level dict in `segqc.heuristics.rule`, not hidden.**
   Intentionally not name-mangled so tests can import it directly for
   snapshot/restore registry isolation. This is documented in the module docstring.

4. **`rules` field on `HeuristicConfig` uses `field(default_factory=dict)`.**
   The dataclass is `frozen=True`, so a mutable default requires `default_factory`.
   The dict itself is not deeply immutable, but the frozen constraint prevents the
   field from being rebound — sufficient for read-only config use.

5. **`load_config` merges `rules` with a shallow replace, not a deep merge.**
   Since `"rules": {}` is in `_DEFAULTS`, the current merge loop (`if key in
   merged: merged[key] = value`) replaces the default empty dict with the file's
   entire `rules` mapping in one shot. This is intentional: partial per-rule
   overrides are handled inside `rule_enabled` / `rule_param` (missing keys fall
   back to defaults), so a shallow file-level replace is sufficient.

6. **`iter_rules()` sorts by `rule_id` string at call time, not at registration.**
   Registration order is unspecified (import order may differ across platforms);
   sorting at call time guarantees deterministic runner output regardless of when
   rules register themselves.

### Initial design intentions (unchanged):

1. **Reuse `segqc.verdict.Severity` for `Finding.severity`** rather than a new
   enum — so findings flow directly into the Stage 1 `Verdict` model in item 034
   without a translation layer.
2. **The feature record is the `build_features_block` dict**, treated as an
   opaque read-only mapping by the core — keeps the engine decoupled from the
   feature dataclasses and trivially serialisable; concrete rules own their own
   sub-key access.
3. **Rules are stateless; thresholds come from config at evaluate time** — makes
   the registry a simple id→instance map and keeps determinism easy.
4. **Per-rule config defaults are supplied by each rule (via `rule_param`'s
   `default`), not baked into the core config** — the engine core stays generic;
   only items 027–033 know their own thresholds and ship their defaults.
5. **No concrete rule families in this item** — strict scope guard so the
   interface is reviewed and stable before seven rule families build on it.

---

## Testing Prerequisites

### Required Services

**None.** Pure Python + standard library; reuses `segqc.verdict` (stdlib-only)
and `segqc.config` (PyYAML). No NumPy/SciPy/NiBabel needed for the engine core.

### Environment Configuration

- **Python:** 3.9+ in `.venv` at project root.
- **Install:** `pip install -e .[dev]`.
- **Environment variables / secrets:** none.

### Manual Validation Checklist

- [ ] **Env current:** `.venv/Scripts/python -c "import segqc"` succeeds.
- [ ] **Import core:** `.venv/Scripts/python -c "from segqc.heuristics import Finding, Rule, run_rules"` succeeds.
- [ ] **Tests pass:** `.venv/Scripts/python -m pytest tests/test_026_rule_engine_core.py`
- [ ] **Full suite green:** `.venv/Scripts/python -m pytest`

### Expected Outcomes

- `Finding` constructs, validates, and round-trips through JSON.
- The runner executes registered/enabled rules deterministically over a feature
  record, tolerating empty rule sets and label-free records without mutation.
- `HeuristicConfig` exposes `rule_enabled` / `rule_param` with documented
  defaults; existing config loading is unaffected.
