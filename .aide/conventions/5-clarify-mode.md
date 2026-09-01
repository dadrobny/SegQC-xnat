## 5. Clarify mode (`loop.clarify` in `aide.toml`)

Controls how `spec-author` resolves an ambiguous queued item:

- **`interactive`** — ask ≤3 targeted questions before writing the spec.
- **`assume`** (unattended default) — pick the most defensible default and record
  each choice in the spec's mandatory **Assumptions** block, which the validator
  surfaces so a human can audit at the queue boundary. Nothing ever hangs.

A spec written before its dependencies are *implemented* must pin their interfaces
as Assumptions; the builder/validator hand back if reality diverged.

**The setting governs `spec-author` and nothing else.** It reads as a global
posture on asking-versus-assuming — it sits under `[loop]`, is named generically,
and is the only such statement in `aide.toml` — and it is not one. `assume` is
defensible for a queued item because its trade is audited: every choice lands in
the spec's mandatory Assumptions block, a human reads it at the queue boundary,
and a wrong item is one unit of a batch, cheap to redo. None of that holds for
the root documents.

**Root documents are authored through their loop entry point, interactively —
whatever `loop.clarify` says.** `vision.md` and `roadmap.md` are Steps 1 and 2
of the loop; the adapter's create-vision / create-roadmap entry points carry the
safeguards a free-hand file write skips — the existing-document check (a vision
is overwritten only after explicit confirmation; a roadmap is updated
incrementally, never regenerated), and the hand-off that presents the result as
a draft for review. Do not write a root document directly, however well the template shape
is known. And root-document authoring is the one part of the loop where a human
is present by construction — the step exists to capture what only they know —
so ask until the mandatory sections are grounded in their answers, and never
fill **Guiding principles**, **Out of scope**, or **Success criteria** from
assumption: a wrong assumption at the root has no Assumptions block to be
audited in, no queue boundary to be caught at, and propagates into the roadmap
and every queue and item derived from it.

**The duty runs both ways.** When several specs are authored before any is built,
the *producing* spec must enumerate the shape its declared consumers read — not
only the API it exposes but the **serialised form**: the JSON layout, which tiers
or records appear in a walk, what a strict mode rejects. Left unpinned, each
consumer independently codes defensively around it — a tolerant reader plus a
hand-back clause where a straight assertion belonged — and one of them eventually
pins an assertion against a shape no code path produces. Pinning it once, in the
spec that owns it, is cheaper than every consumer guessing separately.
