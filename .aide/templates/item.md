<!--
  AIDE work-item template. Step 5. A complete, testable spec — the single source
  of truth for test-writer, builder, and validator. STATIC: it carries NO status
  field (status lives only in progress.md; a header status would just drift).
  Mandatory core (downstream consumers in brackets):
    - Header (Created + pointer to progress.md, Stage, Queue, Objectives, branch)
    - Description                     [builder, test-writer]
    - Acceptance Criteria — atomic, one testable statement each  [test-writer, validator]
    - Assumptions                     [validator surfaces these at the queue boundary]
    - Implementation Steps            [builder]
    - Testing Strategy                [test-writer]
    - Dependencies                    [orchestrator ordering]
    - Decisions & Trade-offs          [builder records as it goes]
  No Docker/services "Testing Prerequisites" boilerplate in the core — enable a
  project-specific block via aide.toml only if the project actually needs it.

  Optional "Environment / Hardware Dependencies" section: include it ONLY when
  this item introduces a capability gated behind an optional package or
  external tool (GPU library, Docker, a large/optional pip extra, ...). Its
  point is to make the eventual real-dependency verification trackable in
  progress.md rather than silently inferred from a green (skip-clean) test
  run — see conventions.md's Environment-Gated Capability Verification rule.
  Omit the section entirely for items with no such capability.

  Fill-in conventions: `{{slot}}` = literal value; _italic line_ = guidance to
  read then replace. Delete this comment in the generated file.
-->
# Item {{nnn}} — {{title}}

> **Created:** {{yyyy-mm-dd}} · status tracked in [`progress.md`](../progress.md)
> **Stage:** {{n}} — {{stage title}}
> **Queue:** [`../queue/queue-{{nnn}}.md`](../queue/queue-{{nnn}}.md) · Item {{nnn}}
> **Objectives:** {{g-codes this item advances}}
> **Suggested branch:** `aide/{{nnn}}-descriptive-name`

---

## Description

_Scope and deliverables, bounded to this one item — what it is and, briefly,
what it is NOT (to fence scope)._

## Acceptance Criteria

_Each criterion atomic, observable, and directly testable — one test per AC,
no guessing. Split any compound "and/or" criterion._

- [ ] **AC1: {{short name}}.** {{observable statement}}

## Assumptions  <!-- MANDATORY: what was assumed when the queued one-liner was ambiguous -->

_Under clarify mode `assume`, record each defensible default taken here (the
validator surfaces them for audit). A spec written before a dependency is
*implemented* pins that interface here as an assumption; the builder/validator
hand back if reality diverged. Write "None." if the item was fully specified._

- {{assumption, and the interface/behaviour it pins}}

## Implementation Steps

_The intended code path in `source_dir` (see `aide.toml`). Ordered, specific._

## Testing Strategy

_What to test: one focused test per AC, plus adversarial / edge cases (empty,
degenerate, malformed, boundary, determinism, immutability). Name the test
module._

## Validation  <!-- OPTIONAL: how to OBSERVE this working, beyond the tests -->

_Only when meaningful observation goes beyond the test suite: a command to
run, output to inspect, a dataset slice to process, a use case to replay. The
validator must EXECUTE this section, not just re-run the tests. If it needs an
environment the loop's machine may lack, name the `[validation]` profile
(checked via `python .aide/scripts/aide.py env --profile <name>`) and the
honest downgrade when absent (record `❓ Unverified`, never a silent pass).
Delete the section if the tests alone genuinely demonstrate the behaviour._

## Dependencies

_Other item numbers this relies on (must be ✅/🚧), and what each provides.
Write "None." if there are none._

## Environment / Hardware Dependencies  <!-- OPTIONAL: delete if not applicable -->

_Only for an item that introduces a capability gated behind an optional
package or external tool (GPU library, Docker, a large/optional pip extra,
...). One row per capability:_

- **{{package/tool name}}** — declared via {{pyproject optional-dependencies
  extra name, or "external tool (not a pip dependency)"}}. Required fallback:
  {{what happens when absent — must degrade gracefully, e.g. skip cleanly,
  never fail, never silently no-op as if the path were exercised}}.
  **Full-capability verification:** not yet exercised with the dependency
  present. Tracked in `progress.md`'s Environment-Gated Capability
  Verification table as `❓ Unverified` until a human or a CI runner with the
  dependency actually runs the gated path — a green skip-clean suite does
  **not** count as verification, and a stage-closing item must add/update
  this table's row for any capability it introduces (see conventions.md).

## Decisions & Trade-offs

To be updated during implementation.
