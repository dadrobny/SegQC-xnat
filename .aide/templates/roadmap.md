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
-->
# <Project> — Development Roadmap

> **Status:** Draft v1 · **Created:** YYYY-MM-DD
> Step 2 of the AIDE loop. Derived from [`vision.md`](vision.md).

---

## Strategy

<The sequencing logic: what is built first and why; where the phase boundaries
are; which objectives each phase prioritises.>

### Objective → stage coverage  <!-- MANDATORY: every vision G-code maps to a stage -->

| Objective | Delivered by |
|-----------|--------------|
| G1 <short> | Stage 1 |
| G2 <short> | Stages 4, 5 |

### Stage dependency graph

```
0 ─► 1 ─► 2 ─► …        <optional ASCII graph of stage dependencies>
```

---

## Stage 0 — <Title>  <!-- MANDATORY shape: one section per stage -->

**Goal.** <One paragraph: the demonstrable capability this stage delivers.>

**Deliverables.**
- <Concrete artifact or capability.>
- <…>

**Dependencies.** <Stage numbers, or "None".>

**Validation / acceptance.**
- <Observable check that the stage is done — becomes progress.md acceptance boxes.>
- <…>

---

## Stage 1 — <Title>

**Goal.** <…>

**Deliverables.**
- <…>

**Dependencies.** <…>

**Validation / acceptance.**
- <…>

<!-- repeat per stage; group into Phases with `# Phase N — <name>` headers if useful -->

---

Next: review, then run `/aide-create-progress`.
