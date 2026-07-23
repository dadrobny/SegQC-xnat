"""A byte-order mark must not change how a project-owned file is read.

Every file this CLI reads is hand-editable — ``aide.toml`` and the ``docs/aide/``
living documents — and Windows editors (Notepad, PowerShell ``Out-File``, several
IDEs' "Save as UTF-8") prepend U+FEFF. Read as plain UTF-8 that codepoint survives
into the text and breaks first-line parsing.

The dangerous case is not a crash. A BOM'd ``aide.toml`` parsed to ``{}`` on the
3.9 fallback parser, so ``load_config`` silently returned pure defaults: the
builder scoped to ``src/`` instead of the project's real ``source_dir``, the git
mode reset — with every command still reporting success. These tests pin the
BOM-tolerant read so that cannot recur.

Stdlib + pytest only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))
import aide  # noqa: E402  (path shim above)

BOM = "﻿"

AIDE_TOML = """\
[project]
name = "RealProject"
source_dir = "src/pkg"
tests_dir = "spec"

[git]
mode = "pr"
main_branch = "trunk"
"""


def _repo(tmp_path: Path, text: str) -> Path:
    (tmp_path / "aide.toml").write_text(text, encoding="utf-8")
    return tmp_path


# --------------------------------------------------------------------------- #
# aide.toml — the silent-default failure
# --------------------------------------------------------------------------- #
def test_bom_prefixed_aide_toml_still_yields_project_facts(tmp_path):
    config = aide.load_config(_repo(tmp_path, BOM + AIDE_TOML))

    assert config["project"]["source_dir"] == "src/pkg"
    assert config["project"]["tests_dir"] == "spec"
    assert config["git"]["mode"] == "pr"
    assert config["git"]["main_branch"] == "trunk"


def test_bom_and_plain_aide_toml_parse_identically(tmp_path):
    plain_root = tmp_path / "plain"
    bom_root = tmp_path / "bom"
    plain_root.mkdir()
    bom_root.mkdir()

    plain = aide.load_config(_repo(plain_root, AIDE_TOML))
    bommed = aide.load_config(_repo(bom_root, BOM + AIDE_TOML))

    assert plain == bommed


def test_a_bom_never_silently_falls_back_to_defaults(tmp_path):
    """The specific regression: defaults returned while the file said otherwise."""
    config = aide.load_config(_repo(tmp_path, BOM + AIDE_TOML))

    assert config["project"]["source_dir"] != aide.DEFAULT_CONFIG["project"]["source_dir"]


def test_the_fallback_parser_is_why_the_read_layer_must_strip_the_bom():
    """Pins the mechanism, and how nasty it is: the parse goes PARTIAL, not empty.

    The 3.9 fallback matches table headers with ``^\\[(...)\\]$``, which a leading
    U+FEFF defeats. Only the FIRST table is lost — every later one parses normally.
    So a BOM'd aide.toml yields a config that is half correct: ``[project]`` gone
    (``source_dir`` silently back to its default) while ``[git]`` is honoured, with
    no error anywhere. That is why the fix belongs at the read layer: by the time
    text reaches a parser the damage is indistinguishable from a short file.
    """
    bommed = aide._parse_toml(BOM + AIDE_TOML)

    assert "project" not in bommed          # first table silently swallowed
    assert bommed["git"]["mode"] == "pr"     # ...while the rest parses fine
    assert aide._parse_toml(AIDE_TOML)["project"]["source_dir"] == "src/pkg"


def test_missing_aide_toml_still_returns_defaults(tmp_path):
    config = aide.load_config(tmp_path)
    assert config["project"]["source_dir"] == aide.DEFAULT_CONFIG["project"]["source_dir"]


# --------------------------------------------------------------------------- #
# docs/aide/ living documents
# --------------------------------------------------------------------------- #
PROGRESS = """\
# Demo — Progress

## Stage 1 — Foundations — 🚧

**Deliverables.**
- ✅ Package. *(Item 001)*
- 📋 Bounds. *(Item 002)*
"""


def _progress_repo(tmp_path: Path, text: str) -> Path:
    (tmp_path / "aide.toml").write_text(AIDE_TOML, encoding="utf-8")
    docs = tmp_path / "docs" / "aide"
    docs.mkdir(parents=True)
    (docs / "progress.md").write_text(text, encoding="utf-8")
    return tmp_path


def test_bom_prefixed_progress_still_parses_item_status(tmp_path):
    root = _progress_repo(tmp_path, BOM + PROGRESS)
    path = root / "docs" / "aide" / "progress.md"

    _, _, status = aide._parse_item_status(
        path.read_text(encoding=aide._ENCODING).splitlines())

    assert status[1] == "complete"
    assert status[2] == "planned"


def test_bom_prefixed_progress_matches_plain(tmp_path):
    bommed = (tmp_path / "b.md")
    plain = (tmp_path / "p.md")
    bommed.write_text(BOM + PROGRESS, encoding="utf-8")
    plain.write_text(PROGRESS, encoding="utf-8")

    assert (bommed.read_text(encoding=aide._ENCODING)
            == plain.read_text(encoding=aide._ENCODING))


# --------------------------------------------------------------------------- #
# the encoding choice itself
# --------------------------------------------------------------------------- #
def test_encoding_is_bom_tolerant():
    assert aide._ENCODING == "utf-8-sig"


def test_utf8_sig_is_lossless_for_non_bom_content(tmp_path):
    """Strictly safer than utf-8: identical when no BOM, and non-ASCII survives."""
    path = tmp_path / "icons.md"
    text = "✅ 🚧 📋 ⏸️ ❌ — em dash, ümlaut\n"
    path.write_text(text, encoding="utf-8")

    assert path.read_text(encoding=aide._ENCODING) == text
