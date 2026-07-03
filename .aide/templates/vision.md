<!--
  AIDE vision template. Step 1 of the loop. The single source of truth the
  roadmap, progress tracker, and every work item derive from.
  Mandatory core (agents/scripts depend on these — do not drop):
    - Guiding principles / constraints  -> validator checks "vision fit" here
    - Out of scope                      -> validator flags scope creep against this
    - Success criteria                  -> roadmap stages must trace back to these
  Everything else is project narrative: keep it concise and specific, no filler.

  Two fill-in conventions (both keep the rendered file readable AND let
  `aide check` catch anything left unfilled):
    - `{{slot}}`     — a literal value to substitute (title, date, a number).
    - _italic line_  — authoring guidance to read, then replace with real prose.
  Delete this comment block in the generated file; the inline MANDATORY
  annotations further down are for framework maintainers and agents, not
  readers of the finished vision — leave those in place.
-->
# {{project-name}} — Project Vision

> **Status:** Draft v1 · **Created:** {{yyyy-mm-dd}}
> Step 1 of the AIDE loop. Source of truth for roadmap, progress, and work items.

---

## 1. Overview

_What is being built and why, in a few sentences — the problem it solves._

## 2. Guiding principles  <!-- MANDATORY: validator checks implementation against these -->

_One bullet per principle. Add as many as the project needs._

- **{{principle name}}.** {{what it constrains, and why}}

## 3. Goals & objectives  <!-- MANDATORY: each G-code is traced by roadmap + progress -->

_One row per objective._

| # | Objective | Measurable outcome |
|---|-----------|--------------------|
| G1 | {{objective}} | {{how it is measured}} |

## 4. Users & use cases

_Who uses it and the concrete workflows they need._

## 5. Core features

_The capabilities that deliver the objectives. Group by area; be specific._

## 6. Technical architecture

_Language/runtime, key libraries, packaging/deployment, data formats, the
high-level data flow._

## 7. Non-functional requirements

_Portability, determinism, performance, reproducibility, maintainability —
whichever the project actually commits to._

## 8. Constraints & assumptions

**Constraints** — {{hard limits: platforms, versions, dependencies}}
**Assumptions** — {{what must hold for the design to work}}

## 9. Out of scope  <!-- MANDATORY: validator flags work that contradicts this -->

_One bullet per exclusion, each with a one-line reason._

- {{excluded item}} — {{one-line reason}}

## 10. Success criteria  <!-- MANDATORY: the project is "done" when these hold -->

_Observable, testable statements — one per criterion._

1. {{success criterion}}

---

Next: start a fresh chat and run `/aide-create-roadmap`.
