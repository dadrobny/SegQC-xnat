"""A malformed ``aide.toml`` must fail loudly, identically, on every Python.

``aide.toml`` states the project's facts — where source lives, the git mode, the
test command. If it cannot be parsed, continuing on defaults means scoping the
builder at the wrong directory and reporting success, so ``load_config`` refuses.

Before this, the two parser paths disagreed on the same file: 3.11's ``tomllib``
raised an uncaught ``TOMLDecodeError`` (a traceback that never named the file),
while the 3.9 fallback *silently accepted* ``name = "unterminated`` and handed
back the truncated text as the value. These tests pin both to one behaviour.

Stdlib + pytest only.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
AIDE_PY = SCRIPTS_DIR / "aide.py"
sys.path.insert(0, str(SCRIPTS_DIR))
import aide  # noqa: E402  (path shim above)

GOOD = """\
[project]
name = "Demo"
source_dir = "src/pkg"

[git]
mode = "pr"
"""

UNTERMINATED = """\
[project]
name = "unterminated
source_dir = "src/pkg"
"""


def _repo(tmp_path: Path, text: str) -> Path:
    (tmp_path / "aide.toml").write_text(text, encoding="utf-8")
    return tmp_path


# --------------------------------------------------------------------------- #
# the happy paths still work
# --------------------------------------------------------------------------- #
def test_valid_config_still_loads(tmp_path):
    config = aide.load_config(_repo(tmp_path, GOOD))
    assert config["project"]["source_dir"] == "src/pkg"
    assert config["git"]["mode"] == "pr"


def test_missing_config_is_not_an_error(tmp_path):
    """Absent means 'unconfigured' — defaults are the right answer."""
    config = aide.load_config(tmp_path)
    assert config["project"]["source_dir"] == aide.DEFAULT_CONFIG["project"]["source_dir"]


def test_empty_config_is_not_an_error(tmp_path):
    config = aide.load_config(_repo(tmp_path, ""))
    assert config["project"]["source_dir"] == aide.DEFAULT_CONFIG["project"]["source_dir"]


def test_comments_and_blank_lines_are_not_an_error(tmp_path):
    text = "# leading comment\n\n[project]\n\n# another\nname = \"Demo\"  # trailing\n"
    assert aide.load_config(_repo(tmp_path, text))["project"]["name"] == "Demo"


@pytest.mark.parametrize("line,expected", [
    # A '#' inside a quoted value is DATA, not a comment — in both quote styles.
    # The single-quoted case regressed silently: comment stripping keyed off
    # `startswith('"')` only, so 'a#b' was truncated to 'a'.
    ('msg = "a#b"', "a#b"),
    ("msg = 'a#b'", "a#b"),
    ('msg = "a"  # real comment', "a"),
    ("msg = 'a'  # real comment", "a"),
    ('msg = "plain"  # a # b', "plain"),
    ("msg = 'C:\\path\\here'", "C:\\path\\here"),   # literal string: no escapes
    (r'msg = "he said \"hi\""', 'he said "hi"'),    # basic string: escaped quotes
    (r'msg = "back\\slash"', "back\\slash"),
    ('msg = ""', ""),
])
def test_quoted_values_are_read_exactly(tmp_path, line, expected):
    config = aide.load_config(_repo(tmp_path, f"[t]\n{line}\n"))
    assert config["t"]["msg"] == expected


# --------------------------------------------------------------------------- #
# malformed -> ConfigError, never a silent default
# --------------------------------------------------------------------------- #
def test_unterminated_string_raises_rather_than_guessing(tmp_path):
    with pytest.raises(aide.ConfigError) as excinfo:
        aide.load_config(_repo(tmp_path, UNTERMINATED))

    message = str(excinfo.value)
    assert "aide.toml" in message          # names the file to go fix
    assert "malformed" in message


def test_the_error_names_the_offending_path(tmp_path):
    root = _repo(tmp_path, UNTERMINATED)
    with pytest.raises(aide.ConfigError) as excinfo:
        aide.load_config(root)

    assert str(root / "aide.toml") in str(excinfo.value)


def test_malformed_config_never_returns_defaults(tmp_path):
    """The regression: a wrong-but-plausible config is worse than a refusal."""
    with pytest.raises(aide.ConfigError):
        aide.load_config(_repo(tmp_path, UNTERMINATED))


def test_fallback_parser_rejects_what_it_used_to_misread():
    """`_parse_toml` is the 3.9 path that silently produced 'unterminated'."""
    with pytest.raises(aide.ConfigError):
        aide._parse_toml(UNTERMINATED)

    assert aide._parse_toml(GOOD)["project"]["name"] == "Demo"


@pytest.mark.parametrize("value", [
    'name = "closed"',
    "name = 'single closed'",
    "queue_cap = 10",
    "clarify = assume",
    "flag = true",
    'path = "C:/has/slashes"',
    'msg = "he said \'hi\'"',
])
def test_well_formed_values_are_not_rejected(value):
    """The strictness must not fire on anything legitimate."""
    assert aide._parse_toml(f"[loop]\n{value}\n")


@pytest.mark.parametrize("value", [
    'name = "open',
    "name = 'open",
])
def test_unterminated_variants_are_rejected(value):
    with pytest.raises(aide.ConfigError):
        aide._parse_toml(f"[project]\n{value}\n")


def test_error_reports_the_line_number():
    with pytest.raises(aide.ConfigError) as excinfo:
        aide._parse_toml('[project]\nname = "Demo"\nsource_dir = "open\n')

    assert "line 3" in str(excinfo.value)


# --------------------------------------------------------------------------- #
# differential: the fallback must not disagree with tomllib about VALUES
# --------------------------------------------------------------------------- #
# Both parsers run in the wild — 3.9 venvs take the fallback, 3.11+ takes tomllib —
# so a value they read differently is a config that means different things on
# different machines. Comparing them directly is what caught the escaped-quote bug:
# the fallback returned 'he said \' where tomllib returned 'he said "hi"'.
DIFFERENTIAL_LINES = [
    'msg = "a#b"',
    "msg = 'a#b'",
    'msg = "a"  # comment',
    "msg = 'a'  # comment",
    'msg = "plain"  # a # b',
    r'msg = "he said \"hi\""',
    r'msg = "back\\slash"',
    "msg = 'C:\\literal\\path'",
    'msg = ""',
    "msg = 'has spaces and, commas'",
    "msg = '__import__(\"x\").y == 0'",   # the shape of a [validation] profile
]


@pytest.mark.skipif(sys.version_info < (3, 11), reason="tomllib needs 3.11+")
@pytest.mark.parametrize("line", DIFFERENTIAL_LINES)
def test_fallback_agrees_with_tomllib_on_values(line):
    import tomllib

    text = f"[t]\n{line}\n"
    assert aide._parse_toml(text)["t"]["msg"] == tomllib.loads(text)["t"]["msg"]


@pytest.mark.skipif(sys.version_info < (3, 11), reason="tomllib needs 3.11+")
@pytest.mark.parametrize("line", [
    'msg = "open',
    "msg = 'open",
    'msg = "a" trailing junk',
])
def test_both_parsers_reject_the_same_malformed_lines(line):
    """They need not raise the same TYPE — load_config normalises that — but
    neither may quietly accept what the other rejects."""
    import tomllib

    text = f"[t]\n{line}\n"
    with pytest.raises(aide.ConfigError):
        aide._parse_toml(text)
    with pytest.raises(tomllib.TOMLDecodeError):
        tomllib.loads(text)


def test_unsupported_escape_is_a_clear_error_not_a_wrong_value():
    """`\\t` is a valid TOML escape this minimal reader does not decode. Rejecting it
    keeps the two parsers from disagreeing silently — the whole point of the PR."""
    with pytest.raises(aide.ConfigError) as excinfo:
        aide._parse_toml(r'[t]' "\n" r'p = "C:\tools"' "\n")

    message = str(excinfo.value)
    assert "unsupported escape" in message
    assert "literal string" in message      # tells the user what to do instead


def test_trailing_characters_after_a_quoted_value_are_rejected():
    with pytest.raises(aide.ConfigError) as excinfo:
        aide._parse_toml('[t]\nmsg = "a" b\n')

    assert "trailing characters" in str(excinfo.value)


# --------------------------------------------------------------------------- #
# the remaining ways a config line can be wrong
# --------------------------------------------------------------------------- #
def test_trailing_backslash_in_a_basic_string_is_rejected():
    """`"abc\\` ends mid-escape: the backslash has nothing to escape.

    Distinct from a plain unterminated string, and worth its own message — the
    fix is different (drop the backslash vs add a closing quote).
    """
    with pytest.raises(aide.ConfigError) as excinfo:
        aide._parse_toml('[t]\nmsg = "abc\\\n')

    assert "unterminated escape" in str(excinfo.value)


def test_a_key_with_no_value_is_rejected():
    with pytest.raises(aide.ConfigError) as excinfo:
        aide._parse_toml("[t]\nmode =\n")

    assert "missing value" in str(excinfo.value)
    assert "'mode'" in str(excinfo.value)


def test_a_key_whose_value_is_only_a_comment_is_rejected():
    with pytest.raises(aide.ConfigError) as excinfo:
        aide._parse_toml("[t]\nmode =  # forgot to fill this in\n")

    assert "missing value" in str(excinfo.value)


def test_an_empty_quoted_value_is_not_a_missing_value():
    """`repo = ""` is a real, intentional value — the framework ships it as the
    default for [framework] repo. It must not trip the missing-value check."""
    assert aide._parse_toml('[t]\nrepo = ""\n')["t"]["repo"] == ""


@pytest.mark.skipif(sys.version_info < (3, 11), reason="tomllib needs 3.11+")
@pytest.mark.parametrize("line", ['msg = "abc\\', "mode ="])
def test_tomllib_also_rejects_these(line):
    """Keeps the two parsers agreeing on which files are readable."""
    import tomllib

    with pytest.raises(tomllib.TOMLDecodeError):
        tomllib.loads(f"[t]\n{line}\n")


# --------------------------------------------------------------------------- #
# the file is there but unusable — distinct from malformed content
# --------------------------------------------------------------------------- #
def test_invalid_utf8_bytes_are_reported_as_malformed(tmp_path):
    """Not valid UTF-8 at all — e.g. a file saved as UTF-16 or cp1252 with
    non-ASCII. Must not surface as a raw UnicodeDecodeError traceback."""
    (tmp_path / "aide.toml").write_bytes(b'[project]\nname = "caf\xe9"\n')

    with pytest.raises(aide.ConfigError) as excinfo:
        aide.load_config(tmp_path)

    message = str(excinfo.value)
    assert "aide.toml" in message
    assert "is malformed" in message


def test_unreadable_file_says_cannot_be_read_not_malformed(tmp_path, monkeypatch):
    """A permissions/IO failure is not a syntax problem — telling the user their
    file is 'malformed' would send them hunting for a typo that isn't there."""
    _repo(tmp_path, GOOD)

    def _boom(*args, **kwargs):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(Path, "read_text", _boom)

    with pytest.raises(aide.ConfigError) as excinfo:
        aide.load_config(tmp_path)

    message = str(excinfo.value)
    assert "cannot be read" in message
    assert "is malformed" not in message


def test_a_directory_named_aide_toml_is_treated_as_absent(tmp_path):
    """`is_file()` is False, so defaults apply rather than an error."""
    (tmp_path / "aide.toml").mkdir()

    config = aide.load_config(tmp_path)

    assert config["project"]["source_dir"] == aide.DEFAULT_CONFIG["project"]["source_dir"]


# --------------------------------------------------------------------------- #
# what the user actually sees at the CLI
# --------------------------------------------------------------------------- #
def test_cli_reports_cleanly_without_a_traceback(tmp_path):
    _repo(tmp_path, UNTERMINATED)

    res = subprocess.run([sys.executable, str(AIDE_PY), "--repo", str(tmp_path), "check"],
                         capture_output=True, text=True, encoding="utf-8")

    assert res.returncode == 2
    assert "Traceback" not in (res.stderr or "")
    assert "error:" in (res.stderr or "")
    assert "aide.toml" in (res.stderr or "")


def test_cli_does_not_refuse_a_valid_config(tmp_path):
    """Guard against the refusal firing on a good file.

    `check` still fails here — the scaffold has no progress.md — but it must fail
    on *that*, having read the config fine, rather than on the config itself.
    """
    _repo(tmp_path, GOOD)
    (tmp_path / "docs" / "aide").mkdir(parents=True)

    res = subprocess.run([sys.executable, str(AIDE_PY), "--repo", str(tmp_path), "check"],
                         capture_output=True, text=True, encoding="utf-8")

    combined = (res.stdout or "") + (res.stderr or "")
    assert "malformed" not in combined
    assert "progress.md" in combined      # got past config, into the real work
