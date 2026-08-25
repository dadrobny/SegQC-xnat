# AIDE conventions

The shared contract every agent, script, and human obeys. Three parts: the
**format contract** for the living documents (so scripts parse them without
heuristics), the **claim protocol** (how "in progress" is signalled), and the
**command hygiene** rules (stated once here; agent specs only point back).

---

## 1. Format contract — `docs/aide/` documents

`.aide/scripts/aide.py` (`check`, `progress set`, `progress accept`, `queue tidy`) and
`scripts/aide_status_report.py` parse these files by exact shape. Deviating from
the shapes below breaks the tooling, so the templates in `.aide/templates/`
model them and `aide check` enforces them.

**Template fill-in conventions** (readable rendered *and* machine-checkable):
a template uses `{{slot-name}}` for a literal value to substitute, and an
_italic line_ for authoring guidance to read then replace with real prose.
Both render as ordinary markdown — nothing is swallowed by a renderer the way
an unescaped `<Placeholder>` tag would be. `aide check` flags any `{{...}}`
left in a generated `docs/aide/**.md` file as an unfilled template slot.
Dates are always **ISO 8601** (`YYYY-MM-DD`) — the templates' `{{yyyy-mm-dd}}`
slot spells the format out so no separate lookup is needed.

**Durable artifacts must read cold.** Everything the loop produces outlives
the session that produced it — item specs, `insights.md` entries, commit
messages, issue bodies, roadmap and progress prose. The reader who matters is
someone opening it months later with none of the conversation, so a durable
artifact is written to be understood with no access to how it was made. Three
rules follow, and they apply wherever the loop writes, not only to the documents
whose shape is fixed above:

1. **No chat-local identifiers.** A label coined for the convenience of one
   conversation — "the second option", "the batch we just scoped", a letter or
   wave assigned while planning — is scaffolding, not a name. It resolves only
   for someone who was there, and a reader who was not cannot even tell what the
   series contained or what happened to the rest of it. Name a thing by what it
   *is*, and title a change by the change, not by the batch it was scheduled in.
2. **Cross-reference by resolvable identity.** An issue number, a file path, a
   commit, a stage number, a dated `insights.md` entry — something a reader can
   look up. Never "the conventions issue", "the companion PR", or "as discussed
   above" pointing outside the artifact.
3. **Record the decision and why it holds, not the route to it.** "My earlier
   lean was wrong", "agreed direction", "settled while drafting" narrate a
   process the reader was not part of, and they age badly: the moment the
   decision is revisited, prose about who once thought what is noise around the
   reasoning that is actually load-bearing. A superseded decision is recorded by
   stating the new one and what changed, not by leaving a trail of leans.

The rules bind interactive sessions as much as unattended ones — a human and a
runtime writing a commit message or an issue body are producing exactly these
artifacts, with no agent spec in play. `.aide/AGENT-CONTEXT.md` exists so they
reach that session without anything having to point at this file.

**Header blockquote** — every living document opens with one, carrying its step
number in the loop, what it derives from, and what derives from it. Those are
structural facts that hold as long as the document exists, so a reader landing
anywhere in `docs/aide/` can place the file without cross-referencing. Keep the
line current when a document's relationships change. The transient hand-off
("run `/aide-…` next") is spoken by the skill that wrote the file, not stored
in it.

### Status icons (the only six)

| Icon | Meaning | Rank |
|------|---------|------|
| 📋 | Planned | 0 |
| 🚧 | In Progress | 3 |
| 🔍 | In Review | 4 |
| ✅ | Complete | 5 |
| ⏸️ | Deferred | 2 |
| ❌ | Excluded | 1 |

Rank is used when one item is referenced on several lines: the most-advanced
status wins.

**✅ means merged — in every `git.mode`.** It is written by `aide merge` when
the merge actually happens, not by an agent ahead of one. 🔍 is the state
between: the work is pushed and awaiting a human's merge. It exists because ✅
used to mean two different things depending on the mode — merged under
`auto-merge`, *pushed and awaiting review* under `pr` — while everything
downstream read it as "done", including `aide gc`, whose default ground is "the
item is ✅" and whose action is `git branch -D` plus a remote delete. The
exhaustion sweep therefore offered to delete the head branch of an open PR, and
the line a human was asked to approve read like confirmation. A run must be
stable under either mode, so the mode no longer changes what a status asserts.

A 🔍 item **holds its stage at 🚧** (an open PR has not shipped) and **holds its
queue open**. `aide check` does not call its claim branch stale, and `aide
status` reports it as awaiting review rather than recommending `gc`. Because in
`pr` mode nothing inside the loop ever observes the merge, `aide sync` and `aide
status` name any 🔍 item whose work has since landed in the base and print the
`aide progress set NNN done` that closes it — the same content check `gc` uses,
so it needs no forge call that could silently degrade to "no open PRs found".

**Structural positions only.** The parsers read icons *only* at structural
positions: a table row's **Status (last) cell**, a stage header's **trailing**
`— <icon>`, and the **leading** icon of a deliverable bullet. An icon anywhere
else — prose, mid-bullet, a title — is plain text and is never read as status,
so authors need not avoid the icon vocabulary in free text. `aide check` still
*warns* on such stray icons in the status-bearing documents (`progress.md`,
queue files) so they stay unambiguous for human readers; other documents are
not scanned.

### `progress.md` (the single source of truth for status)

Mandatory, in order (consumer in brackets):

1. **Stage summary table** — `| Stage | Title | Objectives | Status |` with one
   row per stage; `Stage` is an integer, `Status` a single icon. *(aide check,
   status report, queue-planner)*
2. **Objective coverage table** — `| Objective | Delivered by | Status |`; the
   objective cell starts with a `G<n>` code. *(status report, validator)*
3. **One `## Stage N — <title> — <icon>` section per stage.** Inside it:
   - a **Deliverables** block of **flat** bullets, each
     `- <icon> <text>. *(Item NNN)*` — one status icon, one item ref, no nested
     status-bearing sub-bullets (keep rollup unambiguous). *(builder, validator,
     aide progress, status report)*
   - an **Acceptance** block of `- [ ]` / `- [x]` checkboxes, ticked only by
     `aide progress accept` — never derived. *(validator)*

**Item references on a deliverable bullet.** The `*(Item NNN)*` suffix is what
ties an item to the bullet whose status it moves — `aide progress set NNN` finds
the bullet by it, and `check`/`status`/`claim` derive queue state from it, so an
item no bullet references is untracked. Four forms are accepted, and all four
mean the same thing to every command:

| Form | Reads as |
|---|---|
| `*(Item 006)*` | 6 |
| `*(Items 006, 044)*` | 6, 44 — one deliverable, several items |
| `*(Items 041, 053, 057)*` | 41, 53, 57 — a list is any length |
| `*(Items 089/090)*` | 89, 90 |
| `*(Items 071–075)*` | 71, 72, 73, 74, 75 — inclusive, hyphen or en-dash |
| `*(Items 006, 044–046)*` | 6, 44, 45, 46 — an element may be a range |

Spacing around a separator does not matter. A range spanning more than 50 is
read as a typo and contributes only its endpoints. Prefer the explicit list when
the items are not contiguous; a range is only shorthand for one.

**Rollup rule (deterministic — `aide progress` and `aide check` both apply it):**
a stage is ✅ if *every* Deliverables bullet in it is ✅; then its summary-table
row, section header, and any Objective row delivered solely by complete stages
read ✅ (unless the objective is linked to an Outcome target that is not
`✅ Met` — see below). If any bullet is ✅/🚧 but not all, the stage is 🚧.
Otherwise 📋.

**Acceptance boxes are attestations, and no rollup ever ticks one.** They are
outside the derivation entirely: the rollup skips checkbox lines, `aide check`
never gates a ✅ stage on them, and `aide progress set` leaves them exactly as
the author wrote them. A box is ticked only by a human — or by an agent acting
on a check it actually performed — via:

```
aide progress accept <stage> (--criterion N | --all) [--evidence "<text>"]
```

The reason is that a derived tick is not an attestation. While `progress set`
auto-ticked, a box deliberately left `[ ]` in a ✅ stage — the honest record of
a criterion that shipped unmet — was silently flipped back on the next status
change for *any* item in *any* stage, converting a recorded shortfall into a
false claim that nobody had made. A stage may be ✅ with an unticked box; say
why in an annotation beside it.

**What a stage's ✅ means — and what it deliberately does not.** The rollup
makes stage status track exactly one thing: *the planned work shipped*. An
Acceptance box is therefore an observable check **of the built thing** (the
CLI runs, the artifact validates) — something completing the deliverables can
guarantee. A **measured outcome** the work aims for but cannot guarantee by
construction (an error-rate target, a benchmark result) must NOT be an
Acceptance box: it would hold the stage's honest record hostage to a result the
work cannot promise. Such goals go in the **Outcome targets** table below.

**Outcome targets (optional, additive).** A `## Outcome targets` section in
`progress.md` with one row per measured goal:

```
| Target | Objective | Attempted by | Status | Evidence / follow-up |
|--------|-----------|--------------|--------|----------------------|
| Held-out FPR ≤ 0.10 | G3 | Stage 14 | ❌ Not met | FPR 0.975 → gap insight, item 0NN |
```

Status is table-local (like the env-gated verification table's): `❓
Unverified` until measured, then `✅ Met (date, evidence)` or `❌ Not met
(result → follow-up)`. Semantics *(aide progress, aide check, aide status)*:

- A target **never blocks its stage** — the stage closes when its work ships.
  It gates the **Objective coverage rows** instead: an objective linked to a
  target that is not `✅ Met` cannot roll up to ✅, and `aide check` errors on
  an objective claimed ✅ over a `❌ Not met` target (the goal-level mirror of
  the deliverable-level over-claim error).
- Marking a target `❌ Not met` is a *finding*, so route it like one: append a
  `- [ ] gap — …` line to `insights.md` in the same edit. The feedback loop
  then plans the follow-on deliverables explicitly — needing more work than
  planned to hit a goal is normal, and it enters through the queue, not by
  retro-editing a closed stage's deliverable list.
- `aide status` prints every target not yet `✅ Met`, so the state stays
  visible even though the stage summary table does not carry it.

### `queue-NNN.md`

- **Queue state is derived, not declared.** A queue is **open** iff any of its
  items is 📋/🚧 in `progress.md`, else **done**; "the live queue" is the
  lowest-numbered open one (`aide claim`'s default). A `> **Status:**` line is
  optional decoration for human readers — `aide queue tidy` stamps a completion
  note on superseded queues, and `aide check` warns only when a declared status
  contradicts the derived state. *(aide check, claim, queue tidy)*
- Work items as `### Item NNN: Short Title` + a description paragraph. Item
  numbers are **globally sequential across all queues** — never restart. *(aide
  check, scout/claim, spec-author)*
- **One queue is live at a time, deliberately.** The queue boundary is the human
  checkpoint — one review per batch — so the model offers no concurrency above
  the item level, and a roadmap cannot ask for it. Three senses of "parallel"
  get confused here — the first two are real and useful, the third is the one
  the model does not offer:
  - **Item independence within a queue** — supported: `aide claim` offers any
    unblocked item, so items may be worked in any order. Say this freely.
  - **Stage independence** — a scheduling *fact* ("Stage 19 needs nothing from
    Stage 17"), which tells a planner the two may be queued in either order, or
    merged into one batch if they fit the cap. Write it as independence, not as
    "run alongside": the planner will queue sequentially either way, and the
    softer phrasing only makes roadmap and queues appear to contradict.
  - **Concurrent live queues** — not offered. `loop.claim_scope = "all-open"`
    widens *claiming* across every open queue, but nothing creates a second live
    queue, and the one-queue scope is itself the checkpoint boundary.

### `items/NNN-*.md`

- Filename begins with the zero-padded number. First `#` heading is
  `# Item NNN — Title`. *(status report title parse)*
- **No status field** in the header — status lives only in `progress.md`. The
  header carries `Created`, Stage, Queue, Objectives, Suggested branch, and a
  mandatory **Assumptions** block (see the item template). *(spec-author,
  validator)*
- **`## Dependencies` blocks `aide claim`.** Every item number named in this
  section (any of the accepted forms in the table above) is read as something
  this item is blocked on until it is ✅/🚧 — `aide claim` skips a `📋` item
  while any of its dependencies is still open. Text at or after a literal
  `**Downstream` marker is excluded from that scan, so a forward-looking aside
  ("**Downstream:** item 099 depends on this item's CI job") does not register
  as a backward blocker — put such asides after the marker, never before it.
  *(aide claim)*

### `## Authorised paths` — an item's scope, declared

An item spec declares the files it may change. Writing it down is what turns
"did this item stay in its lane" from a judgement call into a diff against a
list — and it is the only thing that lets two specs authored in the same batch
(`/aide-spec-queue` authors N before any is built) be checked against each other
while changing either is still cheap.

The section is **expected but not required**: it ships in the item template, so
every new spec carries one, and a spec written before this convention stays
workable without a repo-wide back-fill. A tool that reads the section and does
not find it **reports that**, with the remedy — it never silently treats an
undeclared spec as unconstrained.

Shape — two lists of repo-relative paths, one path per bullet, each in backticks
with a short reason:

```
## Authorised paths

**May change:**

- `src/pkg/extract.py` — the new extractor
- `tests/corpus/golden/*.json` — regenerated by this item

**Asserts against:**

- `docs/aide/catalogue.generated.json` — AC7 recomputes its counts live
```

- **May change** — every path this item is authorised to modify. Three forms are
  recognised: an exact path, `dir/**` (the whole subtree), and a single-star
  `dir/*.ext` (one extension in one directory). Prefer the narrowest form that
  covers the work; a subtree wildcard over a directory a sibling item also
  touches is the shape that collides.
- **Asserts against** — files or derived artifacts this item's tests read and
  **pin** without changing. A later item authorised to change one of these
  breaks the assertion, and that collision is findable only if the dependency
  was written down. Include derived artifacts recomputed live, not just files
  compared byte-for-byte: a live recomputation is *more* coupled to the
  underlying state, not less.

**Scope is proved by the diff, not by a hash.** The mechanism is this
declaration checked against the branch's changed files, which is what
`aide scope` does:

```
python .aide/scripts/aide.py scope [NNN] [--base <ref>]
```

With no argument it reads the item number from the current claim branch; a
queue branch resolves to no item and is skipped, since per-item scope is checked
on each claim branch as it merges and a queue branch legitimately aggregates
many items' lists. Whether that per-item check is ever reachable from CI — as
opposed to only from the validator, in-loop — depends on `git.mode`, which
decides whether a claim branch is pushed and whether it ever carries a PR
context; see §4. It diffs against the **merge-base with the item's base** — `--base` if
given, else the branch's recorded base, else `main_branch`, resolved exactly as
§4 describes. The two *derived* answers prefer the `origin/` counterpart over
the local ref, whose merge-base on a checkout sitting behind the work is itself,
so every file the earlier items touched would be reported against this item's
spec. On stacked work the base is the **queue branch**, not `main`: an item
claimed from one has diverged from that, and diffing against `main` would report
every sibling item already merged into the queue.

Exit `0` in scope · `1` something changed outside it · `2` could not check. That third code is the "reported, never silently passed" rule with
teeth: a spec with no section cannot be read as an unconstrained one.

Three paths are authorised for every item without being listed — `progress.md`
and `insights.md`, which the CLI and the roles are mandated to write on any
item, and the item's own spec, where the builder records decisions. A path
declared under **Asserts against** and then changed is reported separately from
an unauthorised one: it means an assertion in this very item now pins state the
item moved.

A test that hashes some
*other* file's bytes against a hardcoded literal to prove this item did not
touch it — a **scope fence** — is a fallback for cases with no diff to check
against, not the norm, and it carries four failure modes that have each cost a
real CI break:

- It **inverts on the next legitimate edit.** The moment a later item is
  authorised to touch the pinned file, the earlier item's test goes red for
  doing exactly what the loop asked. Declare the file under **Asserts against**
  instead, so the conflict surfaces at spec time rather than at first pytest.
- **Never fence a whole tree.** A digest over `src/**` collides with any future
  edit anywhere beneath it. Fence per file, or exclude the paths later items
  name.
- **Never walk untracked or ignored paths.** A tree walk that picks up
  `__pycache__/*.pyc` hashes bytes that embed source mtimes: the "pin" is not
  reproducible even against an unchanged tree.
- **It is platform-fragile in two specific ways.** Any path component entering a
  hash, comparison or match must be `Path.as_posix()` — `str(Path)` renders the
  OS-native separator, so an identical tree hashes differently on Windows. And a
  byte-exact committed fixture needs a `text eol=lf` pin in `.gitattributes`, or
  `core.autocrlf` rewrites it on checkout and the pin never matches.

**Re-pinning.** When a later item is deliberately authorised to change a file an
earlier item pinned, update the earlier constant in the same commit, with a
comment naming the authorising item — do not delete the assertion silently and
do not leave it red. Distinguish the two things a pin can mean: a *diff-time
scope claim* ("item N did not touch X") belongs in **Asserts against** and
should be retired when its item merges, while an *artifact-integrity invariant*
("this released artifact must never change silently") is legitimate and durable
— but then it belongs in a test named for the artifact, living beside it, not
inside an unrelated item's regression module under a `_PRE_NNN_` name.

**One queue's specs are checked against each other before any is built**, in the
window `/aide-spec-queue` creates — N specs on one branch, every cross-item
conflict still cheap to fix:

```
python .aide/scripts/aide.py check --queue NNN [--report <path>]
```

It reports two items claiming the same path under **May change** (warning), one
item changing what another pins under **Asserts against** (error), and a
dependency cycle or a dependency on an item that exists nowhere. `--report`
writes the findings as JSON for a reviewer pass to pick up. The invariant is
worth stating plainly, because a spec-by-spec reading does not give it:
*predicting the one collision a spec happens to name is not the same as proving
no sibling assertion depends on state this item's authorised edit changes.*

**Auditing fences goes by shape, not by name.** The distinguishing feature is a
digest compared against a **hardcoded literal**; a digest compared against a
value computed in the same run is a determinism check and must stay. A sweep for
constants named after item numbers misses every fence named anything else.

### `insights.md` (optional, additive — the compound-engineering inbox)

Where out-of-scope learning goes so it is never lost *and* never acted on out
of scope. Any role, at any time, appends **one line** and returns to its task:

```
- [ ] <type> — <one line> *(item NNN, YYYY-MM-DD)*
```

with `<type>` one of **knowledge** (document it), **defect** (fix it), **gap**
(plan it), **automation** (a recurring manual/agent action deterministic code
could replace — script it), **framework** (belongs to AIDE itself). The item
ref is optional for roles outside an item. `aide check` shape-checks entries
(warning, never error — capture must stay cheap). Template:
`.aide/templates/insights.md` (copy verbatim).

**Capture is a plain append; everything after it has a verb.** Reading and
triaging the file by hand is what made triage expensive enough to defer:

```
python .aide/scripts/aide.py insights list [--open] [--type T] [--trail]
python .aide/scripts/aide.py insights tick N --pointer "<where it landed>"
python .aide/scripts/aide.py insights archive --before YYYY-MM-DD [--yes]
```

`list` numbers entries by position and prints the backlog without the closed
history around it; `tick` performs the one in-place edit below, or appends a
dated trail line when the entry is already ticked; `archive` moves **closed**
entries older than a date into `insights/archive-YYYY-QN.md`, each moved entry
and its trail carried across line for line, and says so — an archive renumbers
what remains, so re-run `list` after one.
Archived entries are frozen and no longer shape-checked, since the immutability
rule leaves no way to act on a warning about one.

**The claim is immutable; its status is not.** The captured line is never
reworded, reordered, or deleted — that is what protects provenance, and it is
load-bearing precisely when an entry turns out to be *wrong*: the wrongness is
the record, and a correction written beneath it teaches what a silent rewrite
would erase. Ticking the checkbox is the one in-place edit.

Status *about* a claim is bookkeeping, and freezing bookkeeping buys nothing. An
entry may carry an **appendable status trail** — dated lines, indented under the
entry, newest last:

```
- [x] framework — <the original claim, never touched> *(item 117, 2026-08-20)*
  - **2026-08-20** → aide-loop issue #50
  - **2026-09-02** → issue rewritten; the original framing overstated the finding
  - **2026-10-11** → resolved in engine 1.16.0
```

A single routing pointer may still be appended to the entry line itself
(`- [x] … → <where it landed>`); the trail is what a *second* update goes in,
and what an entry whose premise decayed needs. Without it there is nowhere to
record that half a claim has since been fixed, so the next reader re-derives all
of it.

**Triage** routes each unchecked entry by type — `knowledge` → the owning
document; `defect`/`gap` → candidate items for the queue being authored (so the
queue PR reviews them); `automation` → a candidate item that adds a CLI
verb/script *and* the skill/agent edit mandating it; `framework` → a GitHub
issue on `[framework] repo` from `aide.toml` (via `gh`; if unset/offline the
entry stays pending).

**When triage happens depends on the destination.** `knowledge`, `defect`,
`gap` and `automation` all land in this project — a document it owns, or a
candidate item — so they wait for the queue boundary (the feedback loop), where
the queue PR reviews the routing. `framework` does not: it leaves for an issue
on another repo, and nothing about that destination needs a queue, so a
`framework` entry may be triaged **on capture or on demand**. Routing it through
the boundary too means the inbox accumulates for exactly as long as a queue
runs, and a long queue is normal.

### Human gates (optional, additive)

A **decision only a person can make**, blocking work until they make it. A
`## Human gates` section in `progress.md`, one row per gate:

```
| Gate | Blocks | Status | Decision / evidence |
|------|--------|--------|---------------------|
| Golden-file retirement approved | 106 | ⏳ Awaiting | — |
| Real segmenter output available | stage 21 | ⏳ Awaiting | — |
```

- **Blocks** — item numbers (any §1 reference form, or bare: `106`,
  `110, 111`, `106–108`), `stage N`, or `all`.
- **Status** — table-local vocabulary, like Outcome targets': `⏳ Awaiting`,
  then `✅ Approved (date)` or `❌ Declined (date)`.

**Why not an acceptance box.** Those are observable checks *of the built thing*
— something completing the deliverables can guarantee. A steering decision is
not that, and overloading the checkboxes would repeat exactly the conflation
Outcome targets were introduced to avoid. Gates get their own table for the
same reason.

**Reach is per gate, and never a queue.** A queue is an *incidental* batch
boundary — part of a stage, one stage, or several small ones — so "the live
queue" names different work from one week to the next while the decision has
not changed. Blocking is tied to the units that mean something:

| Blocks | Reaches | Use when |
|---|---|---|
| `106`, `110, 111`, `106–108` | exactly those items | the decision affects one thread; the queue keeps producing other work |
| `stage N` | every item that stage's deliverables reference, resolved live | the decision could *invalidate* a stage's work, so racing ahead is waste to throw away |
| `all` | every item, everywhere | a programme-level stop — sign-off, budget, legal |

`stage N` resolves through `progress.md` each time it is read, so a gate's reach
follows the roadmap as the stage's contents change rather than freezing a list
written when the gate was raised. Only the person who knows what the pending
decision might change can judge which reach applies, so the table asks them.

**Where a gate is raised, and where it lives.** Same split as Outcome targets:
raised wherever it is noticed, recorded in one place.

- **`roadmap.md`** — a stage whose work needs a decision or an out-of-band
  prerequisite says so in its own section. This is the usual home for a gate
  known at planning time, and it naturally implies `Blocks: stage N`.
- **`items/NNN-*.md`** — a gate discovered while specifying one item is noted
  in its Validation or Assumptions block, implying `Blocks: NNN`.
- **`progress.md`** — the **authoritative row**, always. It is the single source
  of truth for status and the only place the CLI reads, so a gate that exists
  only as prose in a roadmap or a spec blocks nothing.

**Any role may raise a gate; only a person may resolve one.** Creating a blocker
is safe — the worst case is work pausing for a human — so an agent noticing that
a decision is needed should add the row and say so. Removing one is not safe,
and no agent may run `aide gate approve`/`decline`: a gate exists precisely
because the decision is not derivable from the work, so an agent resolving it
destroys the only thing it was protecting.

**A declined gate keeps blocking.** It is resolved — someone decided — but the
decision was "no", so releasing the work would run exactly what was refused.
The remedy is to re-plan: drop the blocked items, or change what the gate asks.
Only `✅ Approved` opens a gate; an unrecognised status blocks too, so a typo
in the mark cannot silently open one.

Semantics *(aide claim, check, status, gate)*:

- **`aide claim` will not offer a blocked item**, and reports the gate as the
  reason rather than an unexplained "none left".
- **`aide check` warns** on every gate still blocking — a normal state, not a
  defect; the point is that it is visible instead of buried in a spec's prose.
- **`aide status`** prints them, like Outcome targets.
- **Resolving is a CLI operation**, never a hand edit:
  ```
  aide gate (list | approve <n> | decline <n>) [--evidence "…"]
  ```

Agents *read* gates — to know why they must stop — and stop.

### Environment-gated capabilities (optional, additive)

A capability gated behind an optional package or external tool (a GPU
library, Docker, a large/optional pip extra, ...) must degrade gracefully —
its tests skip cleanly (never fail, never silently pass as if exercised) when
the dependency is absent, mirroring the project's existing optional-extra
pattern. That graceful-fallback bar is enough for a stage to reach ✅ under the
rollup rule above — **but** a skip-clean pytest run is not evidence the
optional path was ever run for real, and nothing else records that gap by
default. Two additive, non-blocking mechanisms close it:

- The item template's optional **Environment / Hardware Dependencies**
  section — filled in by any item introducing such a capability, naming the
  package/tool, its `pyproject`/equivalent declaration, and the required
  fallback behaviour.
- `progress.md`'s optional **Environment-Gated Capability Verification**
  table — one row per capability, starting `❓ Unverified`. A stage-closing
  item's Implementation Steps must add/update the row(s) for any capability
  its stage introduced. The row flips to `✅ Verified (date, host/CI)` only
  when a human or a CI runner that actually has the dependency present has
  run the gated path — never inferred from the stage's own ✅ status.

Both mechanisms are opt-in: a project with no environment-gated capability
omits them entirely.

Two additions make the verification *planned* rather than hoped-for:

- **`[validation]` environment profiles** (`aide.toml`, optional) — named,
  deterministic environment checks: `<name> = "<python expression>"`, true iff
  the environment provides the capability (e.g.
  `gpu = "__import__('torch').cuda.is_available()"`). Evaluated by
  `aide env --profile <name>` (exit 0 iff satisfied) in the project venv.
- **Stage-validation items** — a queue that closes a roadmap stage ends with a
  `Validate stage N` item that replays the stage's use cases end-to-end and
  updates the capability table (✅ Verified where the profile is satisfied,
  else an explicit ❓ Unverified with the reason). Item specs may also carry an
  optional **Validation** section (see the item template) that the validator
  must execute — tests prove the code runs; validation observes that it does
  something meaningful.

---

## 2. Claim protocol — how "in progress" is signalled

`progress.md`'s `🚧` edit lives on a feature branch and is invisible on `main`
until merge, so it is **not** the mid-flight signal. The shared "this item is
taken" signal is the **pushed `<branch_prefix>NNN-*` branch** (config
`git.branch_prefix`, default `aide/`). `aide claim` owns this:

1. `git fetch --all --prune`; list remote `aide/*` branches.
2. Read the live queue (lowest-numbered open queue) + `progress.md`; pick the
   **first** item that is 📋, whose dependencies are all ✅, and that has no
   existing `aide/NNN-*` branch. With `loop.claim_scope = "all-open"` in
   `aide.toml`, claiming scans **every** open queue in number order instead —
   opt-in, because the one-queue scope is also the human-checkpoint boundary.
3. Create and push `aide/NNN-short-name` (push depends on `git.mode`; `local`
   mode does not push and so has no multi-machine claim signal).

**The two branch shapes that are not claims** — `<prefix>queue-NNN` (a queue is
planned and run on it) and `<prefix>specs-queue-NNN` (its specs are authored on
it) — are created by `aide queue start NNN [--specs]`, never typed by hand. The
engine both *constructs* and *recognises* all three shapes from one definition,
so a name it produces is a name it can parse. A hand-typed name that misses the
shape is not a cosmetic problem: `aide claim` infers an item's base only from a
**recognised** queue branch, so an unrecognised one sends every item's merge to
`main_branch` instead of the queue branch, silently. `queue start` also records
the branch's own base, which `claim` alone could not do.

One person (or one loop) owns an item at a time. Abandoning an item means
deleting its remote branch so the item returns to the pool; `aide check` flags a
claim branch whose item is already ✅ (stale claim), and `aide gc` deletes such
branches — local and remote — deterministically (dry-run by default, `--yes` to
act; `--merged` also collects branches already merged into main).

**`gc` asks git, not the document.** A ✅ is a claim made by a document that
agents and humans both edit, and the action it triggers is `git branch -D` plus
a remote delete — unrecoverable on a plain git host. So on the ✅ ground `gc`
deletes a branch only when `git merge-tree --write-tree` says merging it into
the base would change nothing: the content question, which (unlike `git branch
--merged`) stays correct across a squash merge, and which also strengthens
`--merged`. A ✅ item whose branch still carries unlanded content is **skipped**
with the base named; `--abandon` deletes it anyway, for the genuinely abandoned
claim. `merge-tree --write-tree` needs git ≥ 2.38 — on older git the ✅ ground
refuses rather than falling back to a weaker test, so old git is always *more*
conservative.

**The preview is the set `--yes` acts on.** Every skip — checked out, unlanded,
git too old — is decided before anything is printed and shown as `skipping <br>:
<reason>` on both paths. A dry run a human is asked to approve must not overstate.

---

## 3. Command hygiene (canonical rules)

These rules keep shell commands robust, legible, and failure-localised on **any**
runtime — they hold whether or not a runtime has a permission model. This section
is the single canonical statement of the rules and their rationale; each
agent/command carries a short *positive-form primer* of the same rules so the
correct shape is in context up front (fewer wasted retries). How these rules are
**enforced**, and any provider-specific **command shaping** a permission policy
demands on top of them, are *adapter* concerns — see the adapter's README.

The rules (runtime-general):

- **If an `aide` verb covers it, the raw git form is wrong.** Session preflight
  (fetch, clean-tree check, landing on the right branch) is `aide sync
  [--item NNN]`; claiming is `aide claim`; starting a queue or specs-queue
  branch is `aide queue start NNN [--specs]`; landing is `aide merge`; branch
  clean-up is `aide gc`; checking a branch's changed files against its item's
  authorised paths is `aide scope`. Do not improvise the equivalent `git
  fetch`/`git status`/`git switch -c`/`git diff --name-only` sequences — the verbs
  exist so every run does these steps identically and no step is forgotten.
- **One command per call.** Never chain with `&&` or `;` — separate calls localise
  failures and keep each invocation legible.
- **No `cd` prefix and no directory-changing wrapper** — `git -C "<path>"`,
  `git --git-dir=<path>`, `git --work-tree=<path>`, or a `GIT_DIR=<path>`/
  `GIT_WORK_TREE=<path>` prefix all point git at a repo other than cwd, and
  all four are redundant and brittle the same way `cd` is (a repo path
  containing spaces or apostrophes breaks quoting). The tool's working
  directory is already the repo root — run the bare command. **Unless the repo
  is declared**: a project may legitimately span more than one repo, and an
  adapter may let the operator name the others in personal, machine-local
  config. A command whose repo-override paths all resolve to one declared repo
  is allowed; one naming two different repos stays blocked even when both are
  declared, because history read from one and applied to another's working tree
  is a shape no legitimate workflow needs. Declaring a repo relaxes this rule
  and grants nothing else — the command must still clear whatever permission
  policy the runtime applies.
- **No `2>&1`** or other redirections — the tool already captures stderr.
- **No command substitution in commits.** Avoid `$(…)`/backticks; use single-line
  `-m "msg"`, repeated `-m` for paragraphs, or `git commit -F <file>`.

The `aide` CLI always runs as `python .aide/scripts/aide.py <cmd>` — stdlib-only
and venv-independent, so it works before any project venv exists and identically
across runtimes.

---

## 4. Git modes (`git.mode` in `aide.toml`)

Enforced **only** inside `aide claim` / `aide merge`; agent instructions are
identical across modes.

- **`auto-merge`** (default) — claim branch pushed; on validator PASS `aide merge`
  direct-merges to `main`, re-runs the test command, deletes the claim branch.
- **`pr`** — claim identical; on PASS `aide merge` pushes the branch and **stops**
  ("open a PR"). The human opens the PR (`gh pr create` stays `ask`-gated).
- **`local`** — no pushes at all (offline). Claim is a local branch only (no
  multi-machine signal); merge is local into `main`.

**The mode also decides what kind of CI gate can see a claim branch — pick it for
that too.** Per-item scope is checked as each claim branch merges (§1). Whether a
CI job can run that check depends on what the mode leaves behind for CI to
trigger on:

| `git.mode` | Claim branch pushed | PR opened | Per-item scope gate in CI |
|---|---|---|---|
| `auto-merge` | yes | no | **push-triggered only** — and see the caveats below |
| `pr` | yes | yes, by the human | **works**, in PR context |
| `local` | no | no | **unreachable** — nothing leaves the machine |

The distinction that matters is **PR context**, not visibility. `auto-merge`
pushes the claim branch like `pr` does, so a push-triggered workflow matching
`<branch_prefix>**` (§2 — default `aide/**`) can see it — but there is no pull request, so no `github.base_ref` to
diff against: the job must supply `--base` itself, and it races the in-loop
merge, which deletes the branch as soon as the item lands. Under `pr` the PR
carries both refs — head `aide/NNN-…`, base the item's recorded base — which is
exactly the diff `aide scope` wants, with no branch-name parsing at all.

So the trade is real in both directions. `auto-merge` buys unattended throughput
and, unless a push workflow is deliberately built for it, leaves the gate
enforced **only** by the validator running `aide scope` in-loop: same machine,
same platform, same checkout that built the item — the §7 blind spot exactly.
`pr` buys the independent, second-platform signal back and costs one human PR
open per item.

Choose deliberately rather than inheriting the default, because **a scope job
written for PR context is green forever under `auto-merge` while checking
nothing**: with no PR it either never triggers, or triggers on a branch whose
name yields no item number and correctly skips. A gate can decay this way from a
mode change alone, long after it was correctly built.

The branch *shape* is an independent axis and does not decide this: under the
stacked queue-branch model below, `pr` still works, since the PR's head is the
`aide/NNN-` claim branch and its base is the pushed queue branch — the right
diff base.

**Where "`main`" above actually means "the base".** `main_branch` is the default
and is never removed as one, but real work stacks: a queue branch carries the
queue file, a roadmap deliverable and every item spec, and lands as **one**
reviewed PR — so each of its items must branch off *and merge back into* that
branch, not `main`. Two things make that work without a flag at every call site:

- **`aide claim` records what it branched off.** It already creates the branch
  from whatever is checked out, so claiming from a queue branch has always
  branched correctly; it now remembers that as the item's base. Inference is
  deliberately narrow — only a *recognised* queue branch (`<prefix>queue-NNN`,
  `<prefix>specs-queue-NNN`), never an arbitrary checked-out branch, which
  would silently retarget a merge.
- **`aide merge` returns the item to its recorded base**, so the validator's
  documented `aide merge NNN` step is correct on a queue branch with no change.

`--base <ref>` overrides on `claim`, `merge`, `gc` (which ref `--merged` is
measured against), `status` (what ahead/behind is reported from) and `scope`
(what the diff is taken against). Resolution is always **`--base` > recorded >
`main_branch`**. The record is local git config, not a committed file: the base
is a fact about this checkout's branching, so a different machine falls back to
`main_branch` and passes `--base` explicitly.

**A base is always a local branch**, and a claim always *branches from* it — the
branch's starting point and its recorded base are the same commit by
construction, so an item can never merge back somewhere it did not come from. A
tag, a raw commit or a remote-tracking ref (`origin/main`) is refused rather
than accepted: `git switch` would detach HEAD, and a merge into a detached HEAD
updates no branch while still reporting success.

---

## 5. Clarify mode (`loop.clarify` in `aide.toml`)

Controls how `spec-author` resolves an ambiguous queued item:

- **`interactive`** — ask ≤3 targeted questions before writing the spec.
- **`assume`** (unattended default) — pick the most defensible default and record
  each choice in the spec's mandatory **Assumptions** block, which the validator
  surfaces so a human can audit at the queue boundary. Nothing ever hangs.

A spec written before its dependencies are *implemented* must pin their interfaces
as Assumptions; the builder/validator hand back if reality diverged.

**The duty runs both ways.** When several specs are authored before any is built,
the *producing* spec must enumerate the shape its declared consumers read — not
only the API it exposes but the **serialised form**: the JSON layout, which tiers
or records appear in a walk, what a strict mode rejects. Left unpinned, each
consumer independently codes defensively around it — a tolerant reader plus a
hand-back clause where a straight assertion belonged — and one of them eventually
pins an assertion against a shape no code path produces. Pinning it once, in the
spec that owns it, is cheaper than every consumer guessing separately.

---

## 6. Test hygiene (portability, and tests that can actually fail)

Runtime-general, like §3 — an adapter's test-writing role points back here
rather than restating it.

**Every rule below was earned by a defect that passed every gate this loop runs
and reached `main` anyway.** That is the structural point: spec → tests → build
→ validate → merge all execute in one place, on one platform, against one
checkout, so a defect invisible under those conditions is invisible to the
entire loop, indefinitely. Each was caught by a human reading a CI log, or by a
reviewer outside the loop — never by a gate inside it.

**Portability.**

- **Never write the repo's own working-directory path literally into a test.**
  Resolve from the test file (`Path(__file__).resolve().parents[N]`). An
  absolute path ignores where the process runs, so it passes on the machine
  that authored it — including a fresh clone in a *different* directory — and
  matches nothing anywhere else. Recorded: a hardcoded sandbox path made a glob
  return nothing on every CI runner, collapsing a digest to SHA-256-of-empty
  input and failing all four legs while every local gate stayed green.
- **Any `Path` entering a hash, comparison, or match must be `.as_posix()`.**
  `str(Path)` — including a `Path` interpolated into an f-string, which calls
  `str()` — renders the OS-native separator, so an identical tree hashes
  differently on Windows. This class alone has caused four separate CI-only
  failures.
- **A committed byte-exact fixture needs a `.gitattributes` `text eol=lf` pin.**
  Without it `core.autocrlf` rewrites the file on checkout and every byte
  comparison against it fails on Windows only. `aide check` warns on the cases
  it can decide: a path built from literals, compared with `==` or fed to a
  hash, resolving to a file that exists in the checkout and is covered by no
  `eol=lf` pattern. It reports **only what it can resolve** — a fixture reached
  through a `tmp_path`, a function argument, or a constant imported from
  another package is skipped in silence rather than guessed at, because the
  majority of `read_bytes()` calls in a real suite compare two freshly
  generated files to each other and need no pin at all. Treat a warning as
  authoritative and its silence as partial: the pin is still your
  responsibility on a path the check cannot see.

**Tests that can actually fail.**

- **Prefer calling the function over shelling out to the command that calls
  it.** The CLI's logic is importable and returns structured data; a subprocess
  boundary adds stdout encoding, platform quirks, and a re-parse of what was
  structured a moment earlier. Recorded: `capture_output=True, text=True`
  returned `stdout is None` on a Windows runner — documented not to happen —
  and the fix was to delete the boundary, not harden it.
- **Assert a derived value is recognisable *before* asserting anything about
  it.** A glob that matched nothing, a capture that came back empty, a slice
  taken from a failed `find()` — each yields a value that flows into the
  assertion and passes while checking nothing. Had that Windows capture
  returned `""` rather than `None`, the loop over its lines would have iterated
  zero times and the test would have reported PASS having verified nothing.

`aide check` warns when a file under `tests_dir` contains the repository's own
absolute path — the one rule here a script can decide, and the one whose
recorded instance survived every other gate for weeks.

The lints in this section read `tests_dir`, never `docs_dir`, so they do **not**
require the roadmap document set: `aide check` in a repo with no `docs_dir` runs
them, says so in a `notice:`, and exits 0. A repo may adopt these conventions and
the CLI without adopting the loop.

---

## 7. Verify on a platform this loop never runs on

Test hygiene reduces the odds; it does not close the gap. **No role in this loop
sees a non-Linux checkout, a different working directory, or real CI status**,
so the honest response is to look at the one gate that does:

- Once work is pushed, **check the real CI result** rather than inferring it
  from a green local suite. Report what CI actually said, including "no CI is
  configured here" or "it had not finished" — never let a local pass stand in
  for a platform the loop cannot reach.
- When CI is red on a leg that passed locally, treat it as a **portability
  finding first** (§6), not a flake, until the log says otherwise. Every
  recorded instance looked like a content problem and was a platform one.

---

## 8. Reaching into another repository

A project may legitimately span more than one repo — a library and a sibling
programme repo, or a consumer and the framework clone it updates from. `aide.toml`
never records where those live; `[framework] local_path` and `[hygiene] extra_repos`
in the personal, gitignored `.aide/loop/loop.local.toml` do (§3, and the file's own
comments).

**A repository's own instructions bind for work inside it.** Before editing,
committing to, or otherwise acting on a repo that is not the working directory's,
read that repo's instruction file first. Where two repos' rules disagree about a
file, the repo that owns the file wins.

This is a rule and not merely good manners because the failure is silent and the
cost is real. A runtime loads instruction files for the **working directory's**
repo — its root file, and any subdirectory files as it reaches into them. A
sibling repo gets nothing: *"declared as an additional working directory"* does
not imply *"instructions loaded"*. So an agent editing a sibling is working
without rules that were written down, that it would have followed, and whose
absence nothing announces. What is lost is exactly the material that cannot be
inferred from the code — a versioning rule enforced by that repo's own suite, a
merge policy, a path convention that looks like a typo and is not.

The rule holds for a person too, and for an interactive session with no agent
spec in play. It is the case the framework's own maintenance hits hardest: the
documented update workflow edits the framework clone from a consumer's checkout,
which is precisely a session with the framework's instructions unloaded.

**A runtime may automate this.** Where one can inject context on demand, an
adapter should **point** a session at a declared sibling's instruction file the
first time it touches a path inside it — lazily, so a session that never reaches
across pays nothing. A pointer and not the file's contents: the reader then opens
it as it is *now*, which matters most in the case that motivates the rule, where
the session is editing that very file. That is a delivery mechanism and therefore adapter-local
(`ADAPTER-SPEC.md` §8); the rule above is what binds when a runtime has no such
mechanism, which is the same graceful degradation §3's hygiene guard already
relies on.
