### `items/NNN-*.md`

- Filename begins with the zero-padded number. First `#` heading is
  `# Item NNN — Title`. *(status report title parse)*
- **No status field** in the header — status lives only in `progress.md`. The
  header carries `Created`, Stage, Queue, Objectives, Suggested branch, and a
  mandatory **Assumptions** block (see the item template). *(spec-author,
  validator)*
- **An assumption that pins engine behaviour names the engine it was true
  for** — `- **A3 (engine 1.28.1):** …`, the marker `insights.md` provenance
  already carries, in the bold label beside the assumption's own code. A spec
  outlives its branch and the engine moves under it: three merged specs in one
  consumer asserted `aide check` warnings that a later release had
  deliberately removed, one calling their presence "expected output", and
  nothing detected it — `install.py --update` copies a new engine and says
  nothing about the claims it has just falsified. `aide check` warns
  (advisory, never an exit code) when a marked assumption names an engine
  whose **feature line** predates the installed one; a patch release cannot
  falsify a claim about behaviour, so it is silent. Clear it the way every
  other durable record in this loop is corrected — **append**: a re-check goes
  into the marker, `(engine 1.28.1, re-checked 1.36.0)`, and the newest version
  named is the one the claim stands on. A merged spec is never rewritten to
  agree with a later engine; that is the failure mode, not the fix. An
  unmarked assumption is not warned about — the marker is what makes the claim
  checkable, and inventing a version for one is worse than leaving it
  unclaimed. *(spec-author, validator, `aide check`)*
- **`## Dependencies` blocks `aide claim`.** Every item number named in this
  section (any of the accepted forms in the table above) is read as something
  this item is blocked on until that item is **merged** (✅), or leaves the
  queue's way as ❌ excluded or ⏸️ deferred. 🚧 and 🔍 both still block: work
  in progress is not in the base a dependent would branch from, and neither is
  work whose PR is still open. `aide claim` therefore skips a `📋` item while
  any of its dependencies is still open. Text at or after a literal
  `**Downstream` marker is excluded from that scan, so a forward-looking aside
  ("**Downstream:** item 099 depends on this item's CI job") does not register
  as a backward blocker — put such asides after the marker, never before it.
  The rest of any line from a backticked or bold `Blocks:` label on is
  excluded too, so quoting a human-gate row's reach ("waits on Gate 3 —
  `Blocks: items 119, 120, 121`") does not turn the gate's whole reach into
  dependency edges. The markup is what makes it a marker: plain-prose
  "blocks:" excludes nothing, so an English sentence naming real blockers is
  never silently dropped. Keep a reach quote on one line — the exclusion does
  not extend past it. *(aide claim)*

**An acceptance criterion is an invariant over the resulting content — never a
bound on the diff that produced it, and never a premise about a sibling item's
schedule.** *(spec-author, test-writer, validator)* The criterion outlives its
item: its test is still in the suite long after the branch is gone, so a
criterion that cannot be re-checked then is not one the suite can keep. Two
shapes fail that, both recorded in one consumer's queue:

- **A bounded diff against a pre-item baseline.** Once the item merges into the
  branch its baseline is derived from, the two sides of the comparison are the
  same tree: the test is then either vacuous — green while asserting nothing —
  or red, a fixture-sanity guard correctly refusing to compare, and which of
  the two it is depends only on whether the author happened to write the guard.
  Under a stacked queue this arrives on the very next claim, since the queue
  branch tip *is* the post-item state. Assert the property the edit was
  supposed to produce instead. The diff-time half of such a claim — "this item
  did not touch X" — is `aide scope`'s job on the claim branch, declared under
  `## Asserts against`; §1 → authorised paths says what not to write, and
  `aide check` warns on the two literal shapes.
- **A premise about a sibling item's schedule.** "Item NNN has not landed yet"
  is guaranteed to become false, and it breaks in a file the later item's
  Authorised paths do not cover — so the repair needs a spec amendment before
  it can be made at all. Where an earlier item's test must change when a later
  one lands, the later item's spec lists that test file under **May change**
  from the start, and the earlier item declares what it pins under **Asserts
  against**, which is what makes the collision visible at spec time rather than
  at first pytest.
