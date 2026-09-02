"""Tests for the roadmap↔progress acceptance-drift warning — issue #142.

The recorded defect (spine-failure-lab, engine 1.34.0): fifteen of sixteen
stages mirrored their roadmap Validation / acceptance bullets exactly, and the
sixteenth carried a fourth, load-bearing box the roadmap never grew. The mirror
is a stated contract in two shipped documents and was the only §1 contract with
no enforcement at all — and since 1.35.0 `aide progress reword` *refuses* on a
drifted stage, so the silence had become an unexplained refusal with no tool
naming the stages affected.

The lint is deliberately a warning on **counts**, never an error on text: a
stage may be mid-replan, and comparing wording would fire on every honest
tightening `reword` exists to make cheap. A roadmap stage with no Validation /
acceptance block at all is silent — no mirror is a different situation from a
mirror that disagrees.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "aide.py"
_spec = importlib.util.spec_from_file_location("aide_cli_acceptance_drift", _MODULE_PATH)
aide = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = aide
_spec.loader.exec_module(aide)  # type: ignore[union-attr]


PROGRESS = """\
# P

## Stage 1 — Foundations — 🚧

**Deliverables.**
- 📋 The greeter. *(Item 001)*

**Acceptance.**
- [ ] The benchmark runs end to end.
- [ ] The CLI reports a non-zero exit on failure.

## Stage 2 — Hardening — 📋

**Deliverables.**
- 📋 The fuzzer. *(Item 002)*

**Acceptance.**
- [ ] A full corpus pass finds nothing new.
"""

ROADMAP_ALIGNED = """\
# R

## Stage 1 — Foundations

**Validation / acceptance.**

- The benchmark runs end to end.
- The CLI reports a non-zero exit on failure.
- Target: throughput above 100 rps.

## Stage 2 — Hardening

**Validation / acceptance.**

- A full corpus pass finds nothing new.
"""


def _warnings(tmp_path: Path, roadmap: str, progress: str = PROGRESS):
    ddir = tmp_path / "docs" / "aide"
    ddir.mkdir(parents=True, exist_ok=True)
    (ddir / "roadmap.md").write_text(roadmap, encoding="utf-8")
    return aide.acceptance_drift_warnings(ddir, progress.splitlines())


def test_aligned_stages_are_silent(tmp_path: Path):
    assert _warnings(tmp_path, ROADMAP_ALIGNED) == []


def test_a_target_bullet_is_not_counted(tmp_path: Path):
    """Stage 1 lines up only because the Target: bullet is skipped — §1 routes
    a measured outcome to the Outcome-targets table precisely so it is not a
    box, and counting it would report drift on every stage that has one."""
    assert _warnings(tmp_path, ROADMAP_ALIGNED) == []
    without_target = ROADMAP_ALIGNED.replace(
        "- Target: throughput above 100 rps.\n", "")
    assert _warnings(tmp_path, without_target) == []


def test_a_box_the_roadmap_never_grew_is_reported_with_both_counts(tmp_path: Path):
    """The observed shape: the criterion is real and deliberate, and exists
    only in progress.md. Naming the count on each side is enough to act on."""
    drifted = ROADMAP_ALIGNED.replace(
        "- The CLI reports a non-zero exit on failure.\n", "")
    out = _warnings(tmp_path, drifted)
    assert len(out) == 1
    assert out[0].startswith("stage 1:")
    assert "2 acceptance boxes" in out[0]
    assert "1 bullet" in out[0]
    assert "reword" in out[0]


def test_a_bullet_the_progress_never_grew_is_the_same_drift(tmp_path: Path):
    grown = ROADMAP_ALIGNED.replace(
        "- A full corpus pass finds nothing new.\n",
        "- A full corpus pass finds nothing new.\n- The fuzzer runs in CI.\n")
    out = _warnings(tmp_path, grown)
    assert len(out) == 1
    assert out[0].startswith("stage 2:")
    assert "1 acceptance box " in out[0]
    assert "2 bullets" in out[0]


def test_a_drifted_stage_does_not_hide_an_aligned_sibling(tmp_path: Path):
    """One warning per drifted stage, and only per drifted stage — the repair
    is a hand edit of one document, so the reader needs to know which."""
    both = ROADMAP_ALIGNED.replace(
        "- The CLI reports a non-zero exit on failure.\n", "").replace(
        "- A full corpus pass finds nothing new.\n",
        "- A full corpus pass finds nothing new.\n- The fuzzer runs in CI.\n")
    out = _warnings(tmp_path, both)
    assert [w.split(":")[0] for w in out] == ["stage 1", "stage 2"]


def test_a_stage_with_no_acceptance_block_is_silent(tmp_path: Path):
    """No mirror is a different situation from a mirror that disagrees, and
    `reword` already keeps the two apart. Stage 1's section is present with
    prose only — 0 bullets would be drift, no block must not be."""
    blockless = ("# R\n\n## Stage 1 — Foundations\n\nProse only.\n\n"
                 "## Stage 2 — Hardening\n\n**Validation / acceptance.**\n\n"
                 "- A full corpus pass finds nothing new.\n")
    assert _warnings(tmp_path, blockless) == []


def test_a_stage_absent_from_the_roadmap_is_silent(tmp_path: Path):
    only_stage_1 = ROADMAP_ALIGNED.split("## Stage 2")[0]
    assert _warnings(tmp_path, only_stage_1) == []


def test_a_missing_roadmap_is_silent(tmp_path: Path):
    """A repo may adopt progress.md without the root documents (issue #57)."""
    ddir = tmp_path / "docs" / "aide"
    ddir.mkdir(parents=True)
    assert aide.acceptance_drift_warnings(ddir, PROGRESS.splitlines()) == []


def test_padded_and_bare_stage_numbers_still_line_up(tmp_path: Path):
    """`## Stage 06` in one document and `## Stage 6` in the other are the
    same stage — the numeric match `stage_section` already gives `accept`."""
    padded = PROGRESS.replace("## Stage 1 —", "## Stage 01 —")
    drifted = ROADMAP_ALIGNED.replace(
        "- The CLI reports a non-zero exit on failure.\n", "")
    out = _warnings(tmp_path, drifted, progress=padded)
    assert len(out) == 1 and "2 acceptance boxes" in out[0]


def test_reaches_run_checks_as_a_warning_not_an_error(tmp_path: Path):
    """The lint is only useful if `aide check` actually runs it — and a
    consumer with a drifted stage today must keep exiting 0 on it."""
    repo = tmp_path / "repo"
    ddir = repo / "docs" / "aide"
    ddir.mkdir(parents=True)
    (repo / "aide.toml").write_text(
        '[project]\nname = "Demo"\ndocs_dir = "docs/aide"\n', encoding="utf-8")
    (ddir / "progress.md").write_text(PROGRESS, encoding="utf-8")
    (ddir / "roadmap.md").write_text(
        ROADMAP_ALIGNED.replace(
            "- The CLI reports a non-zero exit on failure.\n", ""),
        encoding="utf-8")
    errors, warnings = aide.run_checks(repo, aide.load_config(repo))
    assert any("acceptance box" in w and "roadmap.md" in w for w in warnings)
    assert not any("acceptance box" in e for e in errors)
