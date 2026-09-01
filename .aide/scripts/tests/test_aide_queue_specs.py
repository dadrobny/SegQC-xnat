"""Tests for ``aide check --queue`` — a queue's specs checked against each other.

The window this guards is the one ``/aide-spec-queue`` creates: N specs authored
on one branch before any is built, where every cross-item conflict is possible
and cheap to fix, and nothing looked.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "aide.py"
_spec = importlib.util.spec_from_file_location("aide_cli_qspecs", _MODULE_PATH)
aide = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = aide
_spec.loader.exec_module(aide)  # type: ignore[union-attr]


AIDE_TOML = """\
[project]
name = "Demo"
docs_dir = "docs/aide"
"""

PROGRESS = """\
# Demo — Progress

## Stage summary

| Stage | Title | Objectives | Status |
|-------|-------|-----------|--------|
| 1 | Rules | G1 | 🚧 |

## Objective coverage

| Objective | Delivered by | Status |
|-----------|--------------|--------|
| G1 Rules | Stage 1 | 🚧 |

## Stage 1 — Rules — 🚧

**Deliverables.**
- 📋 A. *(Item 027)*
- 📋 B. *(Item 028)*

**Acceptance.**
- [ ] Rules fire.
"""


def _spec_text(num: int, may=(), asserts=(), deps="None.") -> str:
    lines = [f"# Item {num:03d} — Demo", "", "## Authorised paths", ""]
    if may:
        lines += ["**May change:**", ""]
        lines += [f"- `{p}` — work" for p in may]
        lines.append("")
    if asserts:
        lines += ["**Asserts against:**", ""]
        lines += [f"- `{p}` — pinned" for p in asserts]
        lines.append("")
    lines += ["## Dependencies", "", deps, ""]
    return "\n".join(lines)


#: Item 027 merged (✅ means merged, in every git.mode), 028 still open.
PROGRESS_27_DONE = PROGRESS.replace("- 📋 A. *(Item 027)*", "- ✅ A. *(Item 027)*")

#: Item 027 deferred — recorded and deliberately not scheduled. It is NOT spent:
#: its edit is dormant, and `aide claim` steps over it rather than waiting.
PROGRESS_27_DEFERRED = PROGRESS.replace("- 📋 A. *(Item 027)*", "- ⏸️ A. *(Item 027)*")


def _make_repo(tmp_path: Path, specs: dict, queue_items=(27, 28),
               progress: str = PROGRESS) -> Path:
    repo = tmp_path / "repo"
    d = repo / "docs" / "aide"
    (d / "queue").mkdir(parents=True)
    (d / "items").mkdir(parents=True)
    (repo / "aide.toml").write_text(AIDE_TOML, encoding="utf-8")
    (d / "progress.md").write_text(progress, encoding="utf-8")
    body = "\n\n".join(f"### Item {n:03d}: Thing {n}\nDoes a thing."
                       for n in queue_items)
    (d / "queue" / "queue-003.md").write_text(f"# Demo — Work Queue 003\n\n{body}\n",
                                              encoding="utf-8")
    for num, text in specs.items():
        (d / "items" / f"{num:03d}-thing.md").write_text(text, encoding="utf-8")
    return repo


def _findings(repo: Path, queue: int = 3):
    cfg = aide.load_config(repo)
    return aide.queue_spec_findings(repo, cfg, queue)


# --------------------------------------------------------------------------- #
# patterns_overlap
# --------------------------------------------------------------------------- #
def test_overlap_identical_patterns():
    assert aide.patterns_overlap("src/a.py", "src/a.py")


def test_overlap_subtree_swallows_a_file():
    assert aide.patterns_overlap("src/**", "src/deep/a.py")
    assert aide.patterns_overlap("src/deep/a.py", "src/**")


def test_overlap_glob_covers_a_literal():
    assert aide.patterns_overlap("tests/golden/*.json", "tests/golden/a.json")


def test_no_overlap_between_unrelated_paths():
    assert not aide.patterns_overlap("src/a.py", "src/b.py")
    assert not aide.patterns_overlap("src/**", "tests/a.py")
    assert not aide.patterns_overlap("tests/golden/*.json", "tests/golden/deep/a.json")


def test_two_unrelated_globs_are_not_guessed_at():
    """Deciding that `src/*.py` and `src/a*` might one day both match `src/ab.py`
    would mean guessing at a future tree. The check reports what it can prove."""
    assert not aide.patterns_overlap("src/*.py", "src/a*")


# --------------------------------------------------------------------------- #
# row 1 — two specs claim the same file
# --------------------------------------------------------------------------- #
def test_reports_two_items_claiming_the_same_path(tmp_path: Path):
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/shared.py"]),
        28: _spec_text(28, may=["src/shared.py"]),
    })
    findings, _ = _findings(repo)
    kinds = [f.kind for f in findings]
    assert "may-change-overlap" in kinds
    hit = next(f for f in findings if f.kind == "may-change-overlap")
    assert hit.items == (27, 28) and hit.severity == "warning"


def test_subtree_claim_overlapping_a_sibling_file_is_reported(tmp_path: Path):
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/**"]),
        28: _spec_text(28, may=["src/one.py"]),
    })
    findings, _ = _findings(repo)
    assert any(f.kind == "may-change-overlap" for f in findings)


def test_disjoint_specs_produce_no_findings(tmp_path: Path):
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/a.py"]),
        28: _spec_text(28, may=["src/b.py"]),
    })
    findings, unspecced = _findings(repo)
    assert findings == [] and unspecced == []


# --------------------------------------------------------------------------- #
# rows 2+3 — one spec changes what another pins
# --------------------------------------------------------------------------- #
def test_changing_a_siblings_pinned_path_is_an_error(tmp_path: Path):
    """The recorded shape: item 101 was authorised to edit exactly the files
    items 099/100 had pinned as untouched forever."""
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/cli.py"]),
        28: _spec_text(28, may=["src/other.py"], asserts=["src/cli.py"]),
    })
    findings, _ = _findings(repo)
    hit = next(f for f in findings if f.kind == "changes-pinned-state")
    assert hit.severity == "error"
    assert hit.items == (27, 28)
    assert "027" in hit.message and "028" in hit.message


def test_a_live_recomputed_pin_is_caught_like_a_byte_hash(tmp_path: Path):
    """The instance a fragile-hash survey missed: item 105's AC7 recomputed its
    evidence live, so it was *more* coupled to the state item 106 changed."""
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/feature_docs.py"]),
        28: _spec_text(28, may=["docs/table.md"],
                       asserts=["src/feature_docs.py"]),
    })
    findings, _ = _findings(repo)
    assert any(f.kind == "changes-pinned-state" for f in findings)


def test_a_declared_dependency_exempts_the_pinned_state_pair(tmp_path: Path):
    """The `Validate stage N` shape, reported inert 14 times on one consumer
    queue: item 028 exists to pin what item 027 produces, and says so under
    `## Dependencies`. It is built against a tree that already holds 027's
    edit, so 027 landing cannot break its pin."""
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/cli.py"]),
        28: _spec_text(28, asserts=["src/cli.py"],
                       deps="Item 027 produces the artifacts this item pins."),
    })
    findings, _ = _findings(repo)
    assert findings == []


def test_the_dependency_exemption_is_directional(tmp_path: Path):
    """027 depending on 028 says 027 is built *last* — so its edit does land
    after 028's pin, which is the break the check exists to report."""
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/cli.py"],
                       deps="Item 028 provides the schema."),
        28: _spec_text(28, asserts=["src/cli.py"]),
    })
    findings, _ = _findings(repo)
    assert any(f.kind == "changes-pinned-state" and f.items == (27, 28)
               for f in findings)


def test_a_transitive_dependency_exempts_the_pair(tmp_path: Path):
    """029 → 028 → 027 orders 027 before 029 just as firmly as a direct edge.
    Only the far end of the chain is the pair being judged, and a validate item
    naming one sibling that names the rest is the ordinary way to write it."""
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/cli.py"]),
        28: _spec_text(28, may=["src/b.py"], deps="Item 027 lands first."),
        29: _spec_text(29, asserts=["src/cli.py"], deps="Item 028 lands first."),
    }, queue_items=(27, 28, 29))
    findings, _ = _findings(repo)
    assert [f.kind for f in findings if f.kind == "changes-pinned-state"] == []


def test_an_undeclared_ordering_still_errors_next_to_a_declared_one(tmp_path: Path):
    """The exemption is per pair, not per item: 029 declares 028 and pins what
    both it and 027 change, and only the undeclared half is reported. That
    undeclared ordering is precisely what the check is for."""
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/cli.py"]),
        28: _spec_text(28, may=["src/b.py"]),
        29: _spec_text(29, asserts=["src/cli.py", "src/b.py"],
                       deps="Item 028 lands first."),
    }, queue_items=(27, 28, 29))
    findings, _ = _findings(repo)
    hits = [f for f in findings if f.kind == "changes-pinned-state"]
    assert [f.items for f in hits] == [(27, 29)]


def test_a_deferred_dependency_earns_no_exemption(tmp_path: Path):
    """The exemption rests on the dependency actually holding the dependent
    back. `aide claim` steps over a ⏸️ blocker, so 028 is claimable today and
    would pin a tree 027 has not touched — then 027 is undeferred and lands on
    top of the pin. Declaring the dependency does not make that safe."""
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/cli.py"]),
        28: _spec_text(28, asserts=["src/cli.py"],
                       deps="Item 027 produces the artifacts this item pins."),
    }, progress=PROGRESS_27_DEFERRED)
    findings, _ = _findings(repo)
    assert any(f.kind == "changes-pinned-state" and f.items == (27, 28)
               for f in findings)


def test_a_chain_through_a_deferred_link_earns_no_exemption(tmp_path: Path):
    """029 → 028 → 027 orders nothing if the middle link does not hold: 028 is
    ⏸️, so 029 is claimable before 027 lands. The filter is on the edges, which
    is what makes the transitive case come out right."""
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/cli.py"]),
        28: _spec_text(28, may=["src/b.py"], deps="Item 027 lands first."),
        29: _spec_text(29, asserts=["src/cli.py"], deps="Item 028 lands first."),
    }, queue_items=(27, 28, 29),
       progress=PROGRESS.replace("- 📋 B. *(Item 028)*", "- ⏸️ B. *(Item 028)*"))
    findings, _ = _findings(repo)
    assert any(f.kind == "changes-pinned-state" and f.items == (27, 29)
               for f in findings)


def test_an_in_progress_dependency_still_exempts_the_pair(tmp_path: Path):
    """🚧 and 🔍 hold a dependent back exactly as 📋 does — the item is not in
    the base a dependent would branch from — so the ordering stands and the
    pair stays exempt. The filter is 'does this still block', not 'is this
    untouched'."""
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/cli.py"]),
        28: _spec_text(28, asserts=["src/cli.py"], deps="Item 027 lands first."),
    }, progress=PROGRESS.replace("- 📋 A. *(Item 027)*", "- 🚧 A. *(Item 027)*"))
    findings, _ = _findings(repo)
    assert [f for f in findings if f.kind == "changes-pinned-state"] == []


def test_an_in_flight_pinning_item_keeps_its_exemption(tmp_path: Path):
    """The asymmetry is deliberate — do not "complete" it. Gating on the
    PINNING item's status would fire only outside this check's window (spec
    authoring, where nothing is built yet), and only in a state that already
    took an out-of-band claim. Meanwhile one deliverable bullet attributes its
    icon to every item in its trailing marker, so two items sharing a 🚧
    bullet would lose a legitimate exemption — errors invented on a normal
    in-flight queue, in exchange for a case `progress.md` cannot distinguish
    from that artifact."""
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/cli.py"]),
        28: _spec_text(28, asserts=["src/cli.py"], deps="Item 027 lands first."),
    }, progress=PROGRESS.replace("- 📋 B. *(Item 028)*", "- 🚧 B. *(Item 028)*"))
    findings, _ = _findings(repo)
    assert [f for f in findings if f.kind == "changes-pinned-state"] == []


def test_the_pinned_state_message_names_the_dependency_remedy(tmp_path: Path):
    """A reader who hits the error needs the third way out — the two the
    message used to offer are both wrong for a validate item."""
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/cli.py"]),
        28: _spec_text(28, asserts=["src/cli.py"]),
    })
    findings, _ = _findings(repo)
    hit = next(f for f in findings if f.kind == "changes-pinned-state")
    assert "## Dependencies" in hit.message


def test_a_mutual_dependency_reports_the_cycle_without_hanging(tmp_path: Path):
    """The exemption walks the same edges the cycle check condemns, so it must
    survive a graph that has one — deriving the ordering must not hang on the
    very shape being reported."""
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/cli.py"], deps="Item 028 lands first."),
        28: _spec_text(28, asserts=["src/cli.py"], deps="Item 027 lands first."),
    })
    findings, _ = _findings(repo)
    assert any(f.kind == "dependency-cycle" for f in findings)


def test_built_after_closes_over_a_chain_and_over_a_cycle():
    assert aide._built_after({1: [2], 2: [3], 3: []}) == {1: {2, 3}, 2: {3}, 3: set()}
    # A cycle terminates, and no item is recorded as built after itself.
    assert aide._built_after({1: [2], 2: [1]}) == {1: {2}, 2: {1}}


def test_pinning_a_path_nobody_changes_is_fine(tmp_path: Path):
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/a.py"]),
        28: _spec_text(28, may=["src/b.py"], asserts=["src/untouched.py"]),
    })
    findings, _ = _findings(repo)
    assert findings == []


# --------------------------------------------------------------------------- #
# row 5 — the dependency graph
# --------------------------------------------------------------------------- #
def test_dependency_cycle_is_an_error(tmp_path: Path):
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/a.py"], deps="Item 028 provides the API."),
        28: _spec_text(28, may=["src/b.py"], deps="Item 027 provides the schema."),
    })
    findings, _ = _findings(repo)
    hit = next(f for f in findings if f.kind == "dependency-cycle")
    assert hit.severity == "error"
    assert set(hit.items) == {27, 28}


def test_a_downstream_aside_does_not_create_a_cycle(tmp_path: Path):
    """`**Downstream` marks a forward reference, not a blocker — a plain
    'item NNN depends on this' aside used to register backwards."""
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/a.py"],
                       deps="None.\n\n**Downstream:** item 028 depends on this."),
        28: _spec_text(28, may=["src/b.py"], deps="Item 027 provides the schema."),
    })
    findings, _ = _findings(repo)
    assert not any(f.kind == "dependency-cycle" for f in findings)


def test_unknown_dependency_is_a_warning(tmp_path: Path):
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/a.py"], deps="Item 999 provides it."),
        28: _spec_text(28, may=["src/b.py"]),
    })
    findings, _ = _findings(repo)
    hit = next(f for f in findings if f.kind == "unknown-dependency")
    assert hit.severity == "warning" and hit.items == (27, 999)


def test_dependency_on_a_real_earlier_item_is_not_flagged(tmp_path: Path):
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/a.py"]),
        28: _spec_text(28, may=["src/b.py"], deps="Item 027 provides the schema."),
    })
    findings, _ = _findings(repo)
    assert findings == []


# --------------------------------------------------------------------------- #
# the ✅ discount — a merged item's claims are spent
# --------------------------------------------------------------------------- #
def test_a_completed_items_may_change_claim_is_spent(tmp_path: Path):
    """The recorded shape: item 118 (✅) claimed `spline.py`; item 119 exists to
    rewrite it. The conflict was real while both were live — once 118 merged,
    reporting it for the rest of the queue's life gives 119 an error it cannot
    clear without editing a completed item's spec."""
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/spline.py"]),
        28: _spec_text(28, may=["src/spline.py"]),
    }, progress=PROGRESS_27_DONE)
    findings, _ = _findings(repo)
    assert findings == []


def test_a_completed_items_pin_is_retired(tmp_path: Path):
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/other.py"], asserts=["src/cli.py"]),
        28: _spec_text(28, may=["src/cli.py"]),
    }, progress=PROGRESS_27_DONE)
    findings, _ = _findings(repo)
    assert findings == []


def test_a_completed_item_cannot_break_a_live_pin(tmp_path: Path):
    """The other side of the discount: what a merged item changed, it has
    already changed — the live spec's pin was authored against the result."""
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/cli.py"]),
        28: _spec_text(28, may=["src/other.py"], asserts=["src/cli.py"]),
    }, progress=PROGRESS_27_DONE)
    findings, _ = _findings(repo)
    assert findings == []


def test_conflicts_between_live_items_survive_the_discount(tmp_path: Path):
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/done.py"]),
        28: _spec_text(28, may=["src/shared.py"]),
        29: _spec_text(29, may=["src/shared.py"]),
    }, queue_items=(27, 28, 29),
       progress=PROGRESS_27_DONE.replace(
           "- 📋 B. *(Item 028)*", "- 📋 B. *(Item 028)*\n- 📋 C. *(Item 029)*"))
    findings, _ = _findings(repo)
    hit = next(f for f in findings if f.kind == "may-change-overlap")
    assert hit.items == (28, 29)


def test_a_cycle_among_completed_items_is_inert(tmp_path: Path):
    """A cycle every member of which merged has PROVED its order was
    satisfiable; reporting it as an error for the rest of the queue's life is
    exactly the unclearable-noise shape the discount removes."""
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/a.py"], deps="Item 028 provides the API."),
        28: _spec_text(28, may=["src/b.py"], deps="Item 027 provides the schema."),
    }, progress=PROGRESS_27_DONE.replace("- 📋 B. *(Item 028)*",
                                         "- ✅ B. *(Item 028)*"))
    findings, _ = _findings(repo)
    assert not any(f.kind == "dependency-cycle" for f in findings)


def test_a_cycle_with_a_merged_member_is_broken_at_that_member(tmp_path: Path):
    """027 merged: 028's dependency on it is satisfied, and 027's own spec no
    longer waits on anything — nothing deadlocks."""
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/a.py"], deps="Item 028 provides the API."),
        28: _spec_text(28, may=["src/b.py"], deps="Item 027 provides the schema."),
    }, progress=PROGRESS_27_DONE)
    findings, _ = _findings(repo)
    assert not any(f.kind == "dependency-cycle" for f in findings)


def test_an_excluded_item_is_spent_too(tmp_path: Path):
    """❌ means dropped: claim never offers the item and an excluded dependency
    does not block, so its spec's claims and pins are as unclearable as a
    merged item's."""
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/shared.py"], asserts=["src/cli.py"]),
        28: _spec_text(28, may=["src/shared.py", "src/cli.py"]),
    }, progress=PROGRESS.replace("- 📋 A. *(Item 027)*", "- ❌ A. *(Item 027)*"))
    findings, _ = _findings(repo)
    assert findings == []


def test_a_deferred_item_stays_in_the_path_comparison(tmp_path: Path):
    """⏸️ is dormant, not dead — the deferred work returns, so a conflict with
    its claims is exactly what to surface while re-planning is still cheap."""
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/shared.py"]),
        28: _spec_text(28, may=["src/shared.py"]),
    }, progress=PROGRESS.replace("- 📋 A. *(Item 027)*", "- ⏸️ A. *(Item 027)*"))
    findings, _ = _findings(repo)
    assert any(f.kind == "may-change-overlap" for f in findings)


def test_a_deferred_item_drops_out_of_the_cycle_graph(tmp_path: Path):
    """A deferred dependency does not block `aide claim` (same status set as
    `_pick_item`), so a cycle through a deferred item cannot deadlock."""
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/a.py"], deps="Item 028 provides the API."),
        28: _spec_text(28, may=["src/b.py"], deps="Item 027 provides the schema."),
    }, progress=PROGRESS.replace("- 📋 A. *(Item 027)*", "- ⏸️ A. *(Item 027)*"))
    findings, _ = _findings(repo)
    assert not any(f.kind == "dependency-cycle" for f in findings)


def test_a_spent_items_undeclared_scope_is_not_reported(tmp_path: Path):
    """The warning's remedy — add the section, get a human scope review — is
    unavailable once the item merged; reporting it forever is the unclearable
    noise this discount exists to remove. A LIVE undeclared spec still warns
    (pinned elsewhere in this file)."""
    repo = _make_repo(tmp_path, {
        27: "# Item 027 — Demo\n\n## Description\n\nNo authorised paths here.\n",
        28: _spec_text(28, may=["src/b.py"]),
    }, progress=PROGRESS_27_DONE)
    findings, _ = _findings(repo)
    assert not any(f.kind == "undeclared-scope" for f in findings)


def test_a_spent_items_unknown_dependency_is_not_reported(tmp_path: Path):
    """'A typo here blocks the item forever' is false for an item that already
    merged — nothing is blocked, and the warning could never be cleared."""
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/a.py"], deps="Item 999 provides it."),
        28: _spec_text(28, may=["src/b.py"]),
    }, progress=PROGRESS_27_DONE)
    findings, _ = _findings(repo)
    assert not any(f.kind == "unknown-dependency" for f in findings)


def test_a_cycle_among_live_items_is_still_an_error(tmp_path: Path):
    """The discount must remove only the inert reports — a live cycle is the
    deadlock the check exists to find."""
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/a.py"], deps="Item 028 provides the API."),
        28: _spec_text(28, may=["src/b.py"], deps="Item 027 provides the schema."),
    })
    findings, _ = _findings(repo)
    assert any(f.kind == "dependency-cycle" for f in findings)


# --------------------------------------------------------------------------- #
# a quoted gate reach is not a dependency
# --------------------------------------------------------------------------- #
def test_a_quoted_gate_blocks_list_creates_no_edges(tmp_path: Path):
    """Transcribing the gate row is the natural way to say which gate holds an
    item; the numbers in the quote are the gate's reach, not blockers. Read as
    edges they yielded cycles among items nobody ordered."""
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/a.py"],
                       deps="None. Waits on Gate 3 — `Blocks: items 028, 099.`"),
        28: _spec_text(28, may=["src/b.py"], deps="Item 027 provides the schema."),
    })
    findings, _ = _findings(repo)
    assert not any(f.kind in ("dependency-cycle", "unknown-dependency")
                   for f in findings)


def test_numbers_before_a_blocks_quote_still_block(tmp_path: Path):
    """The exclusion is the line's remainder, not the line: a real dependency
    sharing a line with a gate quote must survive. The bold label is the other
    marked form a transcribed cell takes."""
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/a.py"],
                       deps="Item 028 provides the API. **Blocks**: item 999."),
        28: _spec_text(28, may=["src/b.py"], deps="Item 027 provides the schema."),
    })
    findings, _ = _findings(repo)
    assert any(f.kind == "dependency-cycle" for f in findings)
    assert not any(f.kind == "unknown-dependency" for f in findings)


def test_plain_prose_blocks_is_not_a_marker(tmp_path: Path):
    """Only a backticked or bold `Blocks:` label excludes. An English sentence
    carrying the word states real blockers, and an exclusion plain prose could
    trip would silently drop them — claim would then offer the item early."""
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/a.py"],
                       deps="Hard blocks: Item 028 must land first."),
        28: _spec_text(28, may=["src/b.py"], deps="Item 027 provides the schema."),
    })
    findings, _ = _findings(repo)
    assert any(f.kind == "dependency-cycle" for f in findings)


# --------------------------------------------------------------------------- #
# graceful degradation
# --------------------------------------------------------------------------- #
def test_undeclared_spec_is_reported_never_skipped(tmp_path: Path):
    repo = _make_repo(tmp_path, {
        27: "# Item 027 — Demo\n\n## Description\n\nNo authorised paths here.\n",
        28: _spec_text(28, may=["src/b.py"]),
    })
    findings, _ = _findings(repo)
    hit = next(f for f in findings if f.kind == "undeclared-scope")
    assert hit.severity == "warning" and hit.items == (27,)
    assert "human scope review" in hit.message


def test_unspecced_items_are_counted_not_flagged(tmp_path: Path):
    """A queued item with no spec yet is the normal mid-queue state — that is
    what /aide-spec-queue exists to fill, not a conflict."""
    repo = _make_repo(tmp_path, {27: _spec_text(27, may=["src/a.py"])})
    findings, unspecced = _findings(repo)
    assert unspecced == [28]
    assert findings == []


def test_bookkeeping_files_are_not_an_overlap(tmp_path: Path):
    """Every item writes progress.md and insights.md — `aide scope` authorises
    both without them being listed. Two items 'conflicting' over progress.md is
    the claim protocol working, not a conflict. Observed as 4 of 16 warnings on
    a real consumer queue before this exclusion."""
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/a.py", "docs/aide/progress.md",
                                "docs/aide/insights.md"]),
        28: _spec_text(28, may=["src/b.py", "docs/aide/progress.md",
                                "docs/aide/insights.md"]),
    })
    findings, _ = _findings(repo)
    assert findings == []


def test_pinning_a_bookkeeping_file_is_still_reported(tmp_path: Path):
    """The exclusion is for the overlap check only — pinning progress.md is a
    real assertion, and changing it under one is a real break."""
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["docs/aide/progress.md"]),
        28: _spec_text(28, may=["src/b.py"], asserts=["docs/aide/progress.md"]),
    })
    findings, _ = _findings(repo)
    assert any(f.kind == "changes-pinned-state" for f in findings)


def test_a_spec_that_only_pins_is_still_compared(tmp_path: Path):
    """An empty May change is not 'nothing declared'. A stage-validation item
    changes only the bookkeeping every item may write, while pinning the tree
    it validates — treating that as undeclared would drop exactly the specs
    whose whole purpose is to assert, and miss siblings breaking their pins."""
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/a.py"]),
        28: _spec_text(28, asserts=["src/a.py"]),
    })
    findings, _ = _findings(repo)
    kinds = [f.kind for f in findings]
    assert "changes-pinned-state" in kinds
    assert "undeclared-scope" not in kinds


def test_a_section_with_both_lists_empty_is_undeclared(tmp_path: Path):
    repo = _make_repo(tmp_path, {
        27: _spec_text(27),
        28: _spec_text(28, may=["src/b.py"]),
    })
    findings, _ = _findings(repo)
    assert any(f.kind == "undeclared-scope" and f.items == (27,) for f in findings)


def test_report_without_queue_is_refused(tmp_path: Path, capsys):
    repo = _make_repo(tmp_path, {27: _spec_text(27, may=["src/a.py"])})
    rc = aide.main(["--repo", str(repo), "check", "--report",
                    str(tmp_path / "out.json")])
    assert rc == 2
    assert "--report needs --queue" in capsys.readouterr().err
    assert not (tmp_path / "out.json").exists()


def test_missing_queue_file_is_an_error(tmp_path: Path):
    repo = _make_repo(tmp_path, {27: _spec_text(27, may=["src/a.py"])})
    findings, _ = _findings(repo, queue=99)
    assert findings[0].kind == "missing-queue"


# --------------------------------------------------------------------------- #
# the command
# --------------------------------------------------------------------------- #
def test_check_queue_fails_on_an_error_finding(tmp_path: Path, capsys):
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/cli.py"]),
        28: _spec_text(28, may=["src/other.py"], asserts=["src/cli.py"]),
    })
    rc = aide.main(["--repo", str(repo), "check", "--queue", "3"])
    assert rc == 1
    assert "Asserts against" in capsys.readouterr().out


def test_check_without_queue_is_unchanged(tmp_path: Path, capsys):
    """The cross-spec checks are opt-in: a bare `aide check` must not start
    reporting them."""
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/cli.py"]),
        28: _spec_text(28, may=["src/other.py"], asserts=["src/cli.py"]),
    })
    assert aide.main(["--repo", str(repo), "check"]) == 0
    assert "Asserts against" not in capsys.readouterr().out


def test_report_writes_the_json_seam(tmp_path: Path):
    repo = _make_repo(tmp_path, {
        27: _spec_text(27, may=["src/cli.py"]),
        28: _spec_text(28, may=["src/other.py"], asserts=["src/cli.py"]),
    })
    out = tmp_path / "status" / "queue-003.json"
    aide.main(["--repo", str(repo), "check", "--queue", "3", "--report", str(out)])
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["queue"] == 3
    assert payload["unspecced_items"] == []
    kinds = [f["kind"] for f in payload["findings"]]
    assert "changes-pinned-state" in kinds
    assert payload["findings"][0]["items"] == [27, 28]
