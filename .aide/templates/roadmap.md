<!--
  AIDE roadmap template. Step 2. Breaks the vision into incremental, demonstrable,
  locally-deployable stages (~1 week each). Derived from vision.md.
  Mandatory core:
    - Objective -> stage coverage table   -> progress mirrors it; every G-code mapped
    - One "## Stage N" section per stage with Goal / Deliverables / Dependencies /
      Validation-acceptance                -> queue-planner scopes a queue to one stage;
                                              progress.md is generated from these sections
  Stages are numbered from 0. Completed/in-progress stages are immutable once the
  loop starts; only planned stages may be re-edited. Concise and specific.

  Fill-in conventions: `{{slot}}` = literal value; _italic line_ = guidance to
  read then replace. Delete this comment in the generated file.
-->
# {{project-name}} — Development Roadmap

> **Status:** Draft v1 · **Created:** {{yyyy-mm-dd}}
> Step 2 of the AIDE loop · derived from [`vision.md`](vision.md) · its stages
> are mirrored by [`progress.md`](progress.md) and scoped into the queues.

---

## Strategy

_The sequencing logic: what is built first and why; where the phase boundaries
are; which objectives each phase prioritises._

### Objective → stage coverage  <!-- MANDATORY: every vision G-code maps to a stage -->

_One row per vision objective._

| Objective | Delivered by |
|-----------|--------------|
| G1 {{short}} | Stage {{n}} |

### Stage dependency graph

_Optional ASCII graph of stage dependencies._

```
0 ─► 1 ─► 2 ─► …
```

---

## Stage 0 — {{title}}  <!-- MANDATORY shape: one section per stage -->

**Goal.** {{one paragraph: the demonstrable capability this stage delivers}}

**Deliverables.**

_One bullet per concrete artifact or capability._

- {{deliverable}}

**Dependencies.** {{stage numbers, or "None"}}

**Validation / acceptance.**

_One bullet per observable check — these become the progress.md acceptance
boxes for this stage._

- {{observable check that the stage is done}}

---

_Repeat "## Stage N — Title" per stage. Group stages into phases with a
`# Phase N — name` header above the first stage of the phase, if useful._
