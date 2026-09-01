### `items/NNN-*.md`

- Filename begins with the zero-padded number. First `#` heading is
  `# Item NNN — Title`. *(status report title parse)*
- **No status field** in the header — status lives only in `progress.md`. The
  header carries `Created`, Stage, Queue, Objectives, Suggested branch, and a
  mandatory **Assumptions** block (see the item template). *(spec-author,
  validator)*
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
