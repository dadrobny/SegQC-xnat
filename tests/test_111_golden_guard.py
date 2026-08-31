"""Golden-fixture test hygiene (item 111).

Closes two independent defects in how the ``tests/golden/*.json`` snapshots
were guarded. Originally these were item 016's ``016_features_report.json``
and item 022's ``022_stage3_report.json``; item 126 retired both and
replaced them with one shared, feature-value-free fixture,
``tests/golden/report_format_contract.json`` (see
``docs/aide/golden-decision-table.md``'s Section 1 "retire" rows and its
"## Retirement execution log") -- this module's guarantees carry over
unchanged onto the replacement, which both ``test_016_features_json.py`` and
``test_022_stage3_serialisation.py`` now compare against via the same
module-level ``GOLDEN_PATH`` name this module monkeypatches.

(a) both were the only committed byte-reproducible text fixtures absent from
    ``.gitattributes``, latent only because both consumers compare via
    ``read_text()`` -- AC1-AC4 pin them and confirm the pin doesn't rewrite
    already-clean content, and survey the rest of ``tests/`` for any other
    unpinned exact-match fixture family.
(b) ``test_022_stage3_serialisation.py::test_ac8_golden_snapshot`` used to
    write the golden and ``pytest.skip`` when it was absent -- deleting the
    golden made the check pass. AC5-AC9 pin the fixed behaviour (fail loudly,
    name the path) and confirm it now matches the sibling
    ``test_016_features_json.py::test_ac5_golden_snapshot``, which never had
    the self-healing branch. Item 126's AC11 requires the replacement arrive
    already holding this property.

These tests exercise the real ``test_ac5_golden_snapshot`` /
``test_ac8_golden_snapshot`` functions directly, with their module-level
``GOLDEN_PATH`` monkeypatched to a location under ``tmp_path`` -- never the
committed fixture itself, which stays untouched throughout this module.
"""

from __future__ import annotations

import inspect
import stat
import subprocess
from pathlib import Path

import pytest

import test_016_features_json as mod016
import test_022_stage3_serialisation as mod022

REPO_ROOT = Path(__file__).resolve().parent.parent
GITATTRIBUTES_PATH = REPO_ROOT / ".gitattributes"
GOLDEN_REL = "tests/golden/report_format_contract.json"

# Every family of committed fixture this repo's test suite compares
# byte-exactly against a committed copy (surveyed by hand for AC4 against
# every `.read_bytes()` / golden `.read_text()` comparison under `tests/`;
# everything else found is two freshly-generated files compared to each
# other within one run -- a determinism check, not a committed fixture).
#
# The committed corpus-golden snapshot family's `*.json` pin was removed by
# item 126, which retired the family it named (docs/aide/golden-decision-
# table.md's "## Retirement execution log").
_KNOWN_BYTE_EXACT_FIXTURE_FAMILIES = (
    "tests/corpus/manifest.json",
    "tests/corpus/intensity/manifest.json",
    "tests/corpus/094_pre_migration_snapshot.json",
    "src/segfacet/reference/reference_default.json",
    "docs/aide/feature_catalogue.generated.json",
    "docs/aide/feature_catalogue.generated.md",
    "docs/aide/golden-decision-table.md",
    "tests/golden/*.json",
)


def _assert_missing_golden_fails_loudly(test_func, missing_path: Path) -> None:
    """Call a no-argument golden-snapshot test function and assert it
    neither skips nor silently passes when its (monkeypatched) golden path
    is absent: it must raise, and the raised exception's message must name
    the missing golden's filename (AC6/AC7)."""
    try:
        test_func()
    except pytest.skip.Exception as exc:
        pytest.fail(f"missing golden causes a skip, not a failure: {exc}")
    except BaseException as exc:  # noqa: BLE001 - deliberately broad, see docstring
        assert missing_path.name in str(exc), (
            "failure does not name the missing golden path "
            f"{missing_path.name}: {exc}"
        )
    else:
        pytest.fail(
            f"missing golden ({missing_path.name}) silently passed instead "
            "of failing"
        )


# =========================================================================== #
# AC1/AC2 -- the .gitattributes pin exists and is effective
# =========================================================================== #


def test_ac1_gitattributes_pins_golden_dir():
    """AC1: .gitattributes contains a rule pinning tests/golden/*.json as
    text eol=lf."""
    attrs_text = GITATTRIBUTES_PATH.read_text(encoding="utf-8")
    lines = [line.strip() for line in attrs_text.splitlines()]
    matching = [
        line
        for line in lines
        if line.startswith("tests/golden/*.json") and "eol=lf" in line
    ]
    assert matching, (
        ".gitattributes has no 'tests/golden/*.json ... eol=lf' pin; "
        "report_format_contract.json is the only committed byte-reproducible "
        "text fixture the two consumers compare against"
    )


def test_ac2_check_attr_reports_lf_pin_for_both_files():
    """AC2: `git check-attr text eol -- <path>` reports the LF pin for the
    shared format-contract fixture both test_016 and test_022 compare
    against (item 126 collapsed the former two per-module snapshots into
    this one shared fixture)."""
    result = subprocess.run(
        ["git", "check-attr", "text", "eol", "--", GOLDEN_REL],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    output = result.stdout

    file_lines = [
        line for line in output.splitlines() if line.startswith(f"{GOLDEN_REL}:")
    ]
    assert any("eol: lf" in line for line in file_lines), (
        f"git check-attr does not report an effective eol=lf pin for "
        f"{GOLDEN_REL}:\n{output}"
    )


# =========================================================================== #
# AC3 -- the committed bytes are already CR-free (pin-only precondition)
# =========================================================================== #


@pytest.mark.parametrize("rel_path", [GOLDEN_REL])
def test_ac3_committed_blob_has_no_carriage_returns(rel_path):
    """AC3: the committed blob (as stored in git, independent of the working
    tree's checkout line endings) contains zero \\r bytes -- so pinning
    text eol=lf is a .gitattributes-only change with no content rewrite."""
    result = subprocess.run(
        ["git", "show", f"HEAD:{rel_path}"],
        cwd=REPO_ROOT,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert b"\r" not in result.stdout, (
        f"committed blob {rel_path} already contains \\r bytes; pinning "
        "text eol=lf here would not be a no-op and needs a different, "
        "content-rewriting change"
    )


# =========================================================================== #
# AC4 -- no other unpinned byte-reproducible fixture remains
# =========================================================================== #


def test_ac4_survey_every_byte_exact_fixture_family_is_pinned():
    """AC4: every family of committed fixture the test suite compares
    byte-exactly is pinned text eol=lf in .gitattributes. Surveyed by hand
    against every committed-vs-regenerated comparison under tests/; every
    comparison not covered by _KNOWN_BYTE_EXACT_FIXTURE_FAMILIES compares two
    freshly-generated files to each other within one test run (a determinism
    check), never a committed fixture."""
    attrs_lines = [
        line.strip() for line in GITATTRIBUTES_PATH.read_text(encoding="utf-8").splitlines()
    ]
    missing = [
        family
        for family in _KNOWN_BYTE_EXACT_FIXTURE_FAMILIES
        if not any(
            line.startswith(family) and "eol=lf" in line for line in attrs_lines
        )
    ]
    assert not missing, (
        "these committed byte-exact fixture families have no text eol=lf "
        f"pin in .gitattributes: {missing}"
    )


# =========================================================================== #
# AC5 -- the self-healing branch is gone from test_ac8_golden_snapshot
# =========================================================================== #


def test_ac5_no_self_healing_branch_in_test_ac8():
    """AC5: test_022_stage3_serialisation.py::test_ac8_golden_snapshot no
    longer writes the golden and no longer calls pytest.skip."""
    source = inspect.getsource(mod022.test_ac8_golden_snapshot)
    assert "pytest.skip" not in source, (
        "test_ac8_golden_snapshot still calls pytest.skip on a missing "
        "golden -- a missing golden must fail, not skip"
    )
    assert "write_text(" not in source, (
        "test_ac8_golden_snapshot still writes the golden file itself -- "
        "deleting the committed golden must not make the test self-heal"
    )


# =========================================================================== #
# AC6/AC7 -- a missing golden fails loudly and names the file
# =========================================================================== #


def test_ac6_ac7_missing_golden_fails_loudly_and_names_path(monkeypatch, tmp_path):
    """AC6: with the shared format-contract fixture absent, the test fails
    -- it does not skip and does not pass. AC7: the failure names the
    missing path. Driven by monkeypatching the module's GOLDEN_PATH to a
    file that does not exist under tmp_path, so the real committed fixture
    is never touched."""
    missing_path = tmp_path / "report_format_contract.json"
    assert not missing_path.exists()
    monkeypatch.setattr(mod022, "GOLDEN_PATH", missing_path)

    _assert_missing_golden_fails_loudly(mod022.test_ac8_golden_snapshot, missing_path)


# =========================================================================== #
# AC8 -- the passing path is unchanged
# =========================================================================== #


def test_ac8_passing_path_unchanged():
    """AC8: with the real committed golden present and matching, the test
    passes exactly as before -- comparison semantics untouched. This calls
    the real function unmodified (no monkeypatch), against the real
    committed golden."""
    mod022.test_ac8_golden_snapshot()  # must not raise


# =========================================================================== #
# AC9 -- the sibling stays the model, and the two tests now agree
# =========================================================================== #


def test_ac9_sibling_test_016_unchanged_and_agrees_on_missing_golden(
    monkeypatch, tmp_path
):
    """AC9: test_016_features_json.py::test_ac5_golden_snapshot is unchanged
    (still no self-healing branch), and the two tests' missing-golden
    behaviour now agrees: both fail loudly and both name the missing path."""
    source = inspect.getsource(mod016.test_ac5_golden_snapshot)
    assert "pytest.skip" not in source, (
        "test_016's golden snapshot test -- the model this item follows -- "
        "has grown a skip branch of its own"
    )
    assert "write_text(" not in source, (
        "test_016's golden snapshot test -- the model this item follows -- "
        "has grown a self-healing write branch of its own"
    )

    missing_016 = tmp_path / "report_format_contract_016.json"
    monkeypatch.setattr(mod016, "GOLDEN_PATH", missing_016)
    _assert_missing_golden_fails_loudly(mod016.test_ac5_golden_snapshot, missing_016)

    missing_022 = tmp_path / "report_format_contract_022.json"
    monkeypatch.setattr(mod022, "GOLDEN_PATH", missing_022)
    _assert_missing_golden_fails_loudly(mod022.test_ac8_golden_snapshot, missing_022)


# =========================================================================== #
# Adversarial: golden present but empty
# =========================================================================== #


def test_adv_golden_present_but_empty_fails_with_assertion(monkeypatch, tmp_path):
    """Adversarial: an empty (but present) golden must fail the content
    comparison cleanly -- an AssertionError, not a crash or a silent pass."""
    empty_golden = tmp_path / "report_format_contract.json"
    empty_golden.write_text("", encoding="utf-8")
    monkeypatch.setattr(mod022, "GOLDEN_PATH", empty_golden)

    with pytest.raises(AssertionError):
        mod022.test_ac8_golden_snapshot()


# =========================================================================== #
# Adversarial: golden present with CRLF content
# =========================================================================== #


def test_adv_golden_present_with_crlf_content_is_well_defined(monkeypatch, tmp_path):
    """Adversarial: a golden checked out with CRLF line endings (the exact
    scenario the .gitattributes pin in AC1/AC2 exists to prevent) has
    well-defined behaviour against today's read_text()-based comparison:
    read_text()'s universal-newline translation normalises \\r\\n back to
    \\n, so the CRLF copy still compares equal to the LF-produced report and
    the test passes without raising. (This is exactly why the pin matters
    for a *future* comparison that switches to read_bytes() -- see AC1-AC4 --
    but it means today's comparison itself is predictable, not a crash.)"""
    real_golden_path = mod022.GOLDEN_PATH
    real_golden_text = real_golden_path.read_text(encoding="utf-8")
    crlf_golden = tmp_path / "report_format_contract.json"
    crlf_golden.write_bytes(real_golden_text.replace("\n", "\r\n").encode("utf-8"))
    monkeypatch.setattr(mod022, "GOLDEN_PATH", crlf_golden)

    mod022.test_ac8_golden_snapshot()  # must not raise


# =========================================================================== #
# Adversarial: read-only golden directory
# =========================================================================== #


def test_adv_read_only_golden_directory_still_names_missing_path(
    monkeypatch, tmp_path
):
    """Adversarial: even when the golden's directory cannot be written to, a
    missing golden must fail with a message naming the path -- not an
    unrelated OS permission error. Skips (rather than fails) on platforms
    that don't actually enforce the read-only bit for directory content
    (observed on some Windows configurations), since that would make this
    test flaky rather than informative."""
    readonly_dir = tmp_path / "readonly_golden_dir"
    readonly_dir.mkdir()
    missing_path = readonly_dir / "report_format_contract.json"

    readonly_dir.chmod(stat.S_IREAD | stat.S_IEXEC)
    probe = readonly_dir / "probe.tmp"
    try:
        probe.write_text("x", encoding="utf-8")
    except OSError:
        writable = False
    else:
        probe.unlink()
        writable = True
    if writable:
        readonly_dir.chmod(stat.S_IRWXU)
        pytest.skip(
            "this platform does not enforce directory write permissions "
            "via chmod; cannot exercise a read-only golden directory"
        )

    try:
        monkeypatch.setattr(mod022, "GOLDEN_PATH", missing_path)
        _assert_missing_golden_fails_loudly(
            mod022.test_ac8_golden_snapshot, missing_path
        )
    finally:
        readonly_dir.chmod(stat.S_IRWXU)
