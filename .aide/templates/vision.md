<!--
  AIDE vision template. Step 1 of the loop. The single source of truth the
  roadmap, progress tracker, and every work item derive from.
  Mandatory core (agents/scripts depend on these — do not drop):
    - Guiding principles / constraints  -> validator checks "vision fit" here
    - Out of scope                      -> validator flags scope creep against this
    - Success criteria                  -> roadmap stages must trace back to these
  Everything else is project narrative: keep it concise and specific, no filler.
  Replace <PLACEHOLDERS>; delete these comments in the generated file.
-->
# <Project> — Project Vision

> **Status:** Draft v1 · **Created:** YYYY-MM-DD
> Step 1 of the AIDE loop. Source of truth for roadmap, progress, and work items.

---

## 1. Overview

<What is being built and why, in a few sentences. The problem it solves.>

## 2. Guiding principles  <!-- MANDATORY: validator checks implementation against these -->

- **<Principle>.** <One line: what it constrains and why.>
- <…>

## 3. Goals & objectives  <!-- MANDATORY: each G-code is traced by roadmap + progress -->

| # | Objective | Measurable outcome |
|---|-----------|--------------------|
| G1 | <objective> | <how it is measured> |
| G2 | <…> | <…> |

## 4. Users & use cases

<Who uses it and the concrete workflows they need.>

## 5. Core features

<The capabilities that deliver the objectives. Group by area; be specific.>

## 6. Technical architecture

<Language/runtime, key libraries, packaging/deployment, data formats, the
high-level data flow.>

## 7. Non-functional requirements

<Portability, determinism, performance, reproducibility, maintainability —
whichever the project actually commits to.>

## 8. Constraints & assumptions

**Constraints** — <hard limits: platforms, versions, dependencies.>
**Assumptions** — <what must hold for the design to work.>

## 9. Out of scope  <!-- MANDATORY: validator flags work that contradicts this -->

- <Explicitly excluded, with a one-line reason each.>

## 10. Success criteria  <!-- MANDATORY: the project is "done" when these hold -->

1. <Observable, testable statement of success.>
2. <…>

---

Next: start a fresh chat and run `/aide-create-roadmap`.
