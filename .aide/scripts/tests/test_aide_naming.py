"""Tests for the item/queue **file naming** helpers — see aide.py.

Item numbers and queue numbers share one namespace with no syntactic marker
between them. 1.13.0 centralised that hazard for *branch* names after an
unanchored match let ``gc`` read ``aide/queue-016`` as item 016 and delete an
in-flight queue branch with the only copy of its queue file and specs on it.

Filenames got no equivalent until 1.15.0: the same convention was re-derived as
raw globs and f-strings at thirteen call sites. None of them was wrong, so these
tests do not pin a fixed bug — they pin the convention itself, in the one place
it now lives, with the adversarial inputs that motivated the branch-side fix.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[1] / "aide.py"
_spec = importlib.util.spec_from_file_location("aide_cli_naming", _MODULE_PATH)
aide = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = aide
_spec.loader.exec_module(aide)  # type: ignore[union-attr]


def _touch(directory: Path, *names: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    for name in names:
        (directory / name).write_text("# stub\n", encoding="utf-8")
    return directory


# --------------------------------------------------------------------------- #
# queue_name / queue_number
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("number,expected", [(1, "queue-001"), (16, "queue-016"),
                                             (123, "queue-123"), (1234, "queue-1234")])
def test_queue_name_is_zero_padded_to_three(number, expected):
    assert aide.queue_name(number) == expected


@pytest.mark.parametrize("stem,expected", [
    ("queue-016", 16),
    ("queue-001", 1),
    ("queue-16", 16),                     # unpadded is tolerated on read
    ("queue-016-stage-27", 16),           # a slug after the number (see #55)
    ("queue-1234", 1234),
])
def test_queue_number_parses_a_queue_filename(stem, expected):
    assert aide.queue_number(Path(f"{stem}.md")) == expected


@pytest.mark.parametrize("stem", [
    "specs-queue-015",     # the specs branch's name, not a queue file
    "notes-on-queue-016",  # a consumer's own document that mentions a queue
    "016-add-the-thing",   # an ITEM spec — the collision the anchor exists for
    "queue",
    "queue-",
    "queue-draft",
    "README",
])
def test_queue_number_rejects_everything_that_is_not_a_queue(stem):
    assert aide.queue_number(Path(f"{stem}.md")) is None


def test_queue_number_is_anchored_at_the_start_of_the_stem():
    """The whole point of the helper. An unanchored search finds `queue-016`
    inside any name that merely contains it, which is how 1.13.0's bug read a
    queue branch as a long-finished item."""
    assert aide.queue_number(Path("archive-queue-016.md")) is None


# --------------------------------------------------------------------------- #
# iter_queue_paths / queue_path
# --------------------------------------------------------------------------- #
def test_iter_queue_paths_is_empty_without_a_directory(tmp_path: Path):
    assert aide.iter_queue_paths(tmp_path / "nope") == []


def test_iter_queue_paths_orders_by_number_and_skips_non_queues(tmp_path: Path):
    qdir = _touch(tmp_path / "queue", "queue-002.md", "queue-010.md", "queue-001.md",
                  "specs-queue-003.md", "README.md", "notes.md")
    assert [p.name for p in aide.iter_queue_paths(qdir)] == [
        "queue-001.md", "queue-002.md", "queue-010.md"]


def test_iter_queue_paths_orders_slugged_names_by_number_not_alphabet(tmp_path: Path):
    """Lexicographic order and numeric order agree only while every name is
    exactly the padded number; a slug breaks the tie the wrong way."""
    qdir = _touch(tmp_path / "queue", "queue-002-alpha.md", "queue-010-beta.md",
                  "queue-002.md")
    assert [aide.queue_number(p) for p in aide.iter_queue_paths(qdir)] == [2, 2, 10]


def test_queue_path_resolves_an_existing_queue(tmp_path: Path):
    qdir = _touch(tmp_path / "queue", "queue-001.md", "queue-016.md")
    assert aide.queue_path(qdir, 16).name == "queue-016.md"


def test_queue_path_resolves_a_slugged_queue(tmp_path: Path):
    """Resolving by glob rather than constructing `queue-NNN.md` is the one
    behavioural difference in the helper block, and this is why: adding slugs
    becomes a naming decision, not an engine sweep."""
    qdir = _touch(tmp_path / "queue", "queue-016-stage-27.md")
    assert aide.queue_path(qdir, 16).name == "queue-016-stage-27.md"


def test_queue_path_is_none_when_the_queue_does_not_exist(tmp_path: Path):
    qdir = _touch(tmp_path / "queue", "queue-001.md")
    assert aide.queue_path(qdir, 2) is None
    assert aide.queue_path(tmp_path / "nope", 1) is None


def test_queue_path_matches_padded_and_unpadded_names_alike(tmp_path: Path):
    qdir = _touch(tmp_path / "queue", "queue-7.md")
    assert aide.queue_path(qdir, 7).name == "queue-7.md"


def test_queue_path_does_not_confuse_a_queue_with_a_prefix_of_another(tmp_path: Path):
    qdir = _touch(tmp_path / "queue", "queue-016.md", "queue-160.md")
    assert aide.queue_path(qdir, 16).name == "queue-016.md"
    assert aide.queue_path(qdir, 160).name == "queue-160.md"


# --------------------------------------------------------------------------- #
# item_spec_paths
# --------------------------------------------------------------------------- #
def test_item_spec_paths_is_empty_without_a_directory(tmp_path: Path):
    assert aide.item_spec_paths(tmp_path / "nope", 1) == []


def test_item_spec_paths_finds_the_spec_by_padded_number(tmp_path: Path):
    idir = _touch(tmp_path / "items", "016-add-the-thing.md", "017-other.md")
    assert [p.name for p in aide.item_spec_paths(idir, 16)] == ["016-add-the-thing.md"]


def test_item_spec_paths_takes_an_unpadded_int(tmp_path: Path):
    """Callers hold a number, not a string; padding is the helper's job and was
    re-typed as `f"{n:03d}-*.md"` at five sites before it had one."""
    idir = _touch(tmp_path / "items", "007-lucky.md")
    assert [p.name for p in aide.item_spec_paths(idir, 7)] == ["007-lucky.md"]


def test_item_spec_paths_does_not_match_a_queue_file(tmp_path: Path):
    """The namespace collision, in the items directory: a stray `queue-016.md`
    must not answer a request for item 016."""
    idir = _touch(tmp_path / "items", "queue-016.md")
    assert aide.item_spec_paths(idir, 16) == []


def test_item_spec_paths_does_not_match_a_longer_number(tmp_path: Path):
    idir = _touch(tmp_path / "items", "160-later.md")
    assert aide.item_spec_paths(idir, 16) == []


def test_item_spec_paths_returns_duplicates_sorted_rather_than_raising(tmp_path: Path):
    """The convention permits one spec per number; the filesystem does not.
    Callers take [0], so the order must be deterministic."""
    idir = _touch(tmp_path / "items", "016-b-second.md", "016-a-first.md")
    assert [p.name for p in aide.item_spec_paths(idir, 16)] == [
        "016-a-first.md", "016-b-second.md"]
