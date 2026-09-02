"""``--backend cpu|gpu|auto`` CLI wiring tests for item 075 (AC1-AC8, AC13,
AC14 -- the Part-A half of Stage 10's integration closer).

Item 072's Stage-2/3 feature functions auto-resolve ``backend=None ->
get_backend()`` at call time (honouring the ``SEGFACET_BACKEND`` env var, item
071); ``run_qc``/``evaluate_cohort``/``build_reference`` were never given a
``backend`` parameter to thread. Item 075 exposes that seam as a first-class
``--backend`` flag on all three ``segfacet`` subcommands
(``run``/``evaluate``/``build-reference``) via a shared
``_apply_backend_selection(args)`` helper in ``cli.py`` that eagerly resolves
the flag through ``segfacet.backend.get_backend(override=...)`` (fail-fast on a
forced-but-unavailable GPU) and then sets ``os.environ["SEGFACET_BACKEND"]``
**only** when the flag was explicitly given -- leaving the ambient env var (or
``auto``) to govern when it is omitted. ``cli.py``/``backend.py`` are not
touched by this module; only ``cli.py`` gains production code (the builder's
job).

Every test that reaches a subcommand's compute entry point spies on that
entry point by wrapping the **real** implementation (recording
``os.environ.get("SEGFACET_BACKEND")`` at call time, then delegating) so the run
completes normally and both reports/artifacts are written exactly as before
-- this is what proves the flag reaches the *unmodified* compute path via the
env var alone (A2), not a stubbed/short-circuited one.

This host has no CuPy installed: every "``--backend gpu``" assertion here
exercises the *forced-but-unavailable* failure path (AC5), never a real GPU
run.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

import nibabel as nib
import pytest

from segfacet.backend import cupy_available
from segfacet.cli import _build_parser, main
from segfacet.reference.ingest import DEFAULT_SEG_SUFFIX
from segfacet.synth.clean_gt import build_clean_spine
from segfacet.synth.corpus import CORPUS_DIR

from synthetic import make_labelmap, make_scan, write_nifti

SUBCOMMANDS = ["run", "evaluate", "build-reference"]

# Minimal, placeholder argv per subcommand -- never touches disk since a
# usage-error (SystemExit code 2) from an invalid --backend token fires
# during argparse parsing, before any handler runs (AC2).
_PLACEHOLDER_ARGV = {
    "run": ["run", "--scan", "unused.nii.gz", "--seg", "unused.nii.gz", "--out", "unused_out"],
    "evaluate": ["evaluate", "--cohort", "unused.json", "--out", "unused_out"],
    "build-reference": ["build-reference", "--cohort", "unused_dir", "--out", "unused.json"],
}


# =========================================================================== #
# Fixture helpers
# =========================================================================== #


@pytest.fixture(autouse=True)
def _restore_backend_env():
    """Undo the process-scoped ``SEGFACET_BACKEND`` mutation ``--backend`` makes.

    ``_apply_backend_selection`` sets the variable on ``os.environ`` for the
    rest of the process (A11, deliberate: the compute path reads it at call
    time). A test that calls ``main()`` with the flag and does not go through
    ``monkeypatch`` therefore leaves it set for whatever runs next in the same
    worker -- and the tests below that assert the variable is *absent* then
    depend on which of their siblings happened to run first.

    That is not hypothetical. Before this fixture,
    ``test_adv_env_hermeticity_after_explicit_backend_selection`` passed only
    as a whole-file run (AC3/AC4/AC5 leak ``cpu`` ahead of it, so its
    ``original_present`` branch was the one taken) and failed when run alone.
    ``pytest -n 4`` schedules by test, not by file, which is what turned it red
    on PR #63's two numpy legs while the serial legs stayed green.
    """
    before = os.environ.get("SEGFACET_BACKEND")
    try:
        yield
    finally:
        if before is None:
            os.environ.pop("SEGFACET_BACKEND", None)
        else:
            os.environ["SEGFACET_BACKEND"] = before


def _run_files(tmp_path):
    """A small real scan+seg pair for ``segfacet run`` (load_case is never
    mocked, so this must be a real, loadable fixture)."""
    shape = (12, 12, 12)
    blocks = {20: ((2, 6), (2, 6), (2, 6)), 21: ((6, 10), (6, 10), (6, 10))}
    seg_img = make_labelmap(shape=shape, blocks=blocks, spacing=(1.0, 1.0, 1.0))
    scan_img = make_scan(shape=shape, spacing=(1.0, 1.0, 1.0), gradient=True)
    scan_path = write_nifti(scan_img, tmp_path / "scan.nii.gz")
    seg_path = write_nifti(seg_img, tmp_path / "seg.nii.gz")
    return scan_path, seg_path


def _evaluate_manifest(tmp_path):
    """A one-case cohort manifest referencing a real committed corpus
    fixture (load_cohort_manifest is never mocked)."""
    dst = tmp_path / "fixtures"
    if not dst.exists():
        shutil.copytree(CORPUS_DIR / "fixtures", dst)
    manifest = {
        "manifest_version": 1,
        "cases": [
            {
                "case_id": "clean",
                "gt": "fixtures/clean_control_seg.nii.gz",
                "expected": {"expected_verdict": "pass"},
            }
        ],
    }
    path = tmp_path / "cohort.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def _build_reference_cohort(tmp_path):
    """A minimal real one-subject cohort directory for ``build-reference``."""
    cohort_dir = tmp_path / "cohort"
    cohort_dir.mkdir(parents=True, exist_ok=True)
    spine = build_clean_spine(
        levels=("L1",), spacing=(1.0, 1.0, 1.0), curve_amplitude_mm=4.0
    )
    seg_path = cohort_dir / f"sub-000{DEFAULT_SEG_SUFFIX}"
    nib.save(spine.seg_img, str(seg_path))
    return cohort_dir


def _build_argv(sub, tmp_path, extra=()):
    """Build a valid, minimal argv list for *sub* plus any *extra* flag
    tokens (e.g. ``["--backend", "cpu"]``); returns ``(argv, out_target)``
    where ``out_target`` is the directory (``run``/``evaluate``) or JSON file
    path (``build-reference``) the subcommand writes to."""
    out_dir = tmp_path / "out"
    if sub == "run":
        scan_path, seg_path = _run_files(tmp_path)
        argv = ["run", "--scan", str(scan_path), "--seg", str(seg_path), "--out", str(out_dir)]
        return argv + list(extra), out_dir
    if sub == "evaluate":
        manifest_path = _evaluate_manifest(tmp_path)
        argv = ["evaluate", "--cohort", str(manifest_path), "--out", str(out_dir)]
        return argv + list(extra), out_dir
    if sub == "build-reference":
        cohort_dir = _build_reference_cohort(tmp_path)
        out_path = tmp_path / "artifact.json"
        argv = ["build-reference", "--cohort", str(cohort_dir), "--out", str(out_path)]
        return argv + list(extra), out_path
    raise AssertionError(sub)


def _expected_outputs(sub, out_target):
    """The file(s) a successful *sub* invocation writes to *out_target*."""
    if sub == "run":
        return [out_target / "segfacet_report.json", out_target / "segfacet_report.txt"]
    if sub == "evaluate":
        return [out_target / "eval_report.json", out_target / "eval_report.txt"]
    if sub == "build-reference":
        return [out_target]
    raise AssertionError(sub)


def _install_compute_spy(sub, monkeypatch, recorder):
    """Wrap *sub*'s real compute entry point with a spy that records
    ``os.environ.get("SEGFACET_BACKEND")`` at call time, then delegates to the
    real implementation so the run completes normally (AC4)."""
    if sub == "run":
        # Item 090: reference mode is ON by default, so a default `run`
        # invocation now dispatches through run_qc_with_reference rather
        # than the reference-less run_qc (cli.py's _handle_run).
        import segfacet.pipeline as mod

        original = mod.run_qc_with_reference

        def spy(*args, **kwargs):
            recorder["env"] = os.environ.get("SEGFACET_BACKEND")
            return original(*args, **kwargs)

        monkeypatch.setattr(mod, "run_qc_with_reference", spy)
    elif sub == "evaluate":
        import segfacet.eval.harness as mod

        original = mod.evaluate_cohort

        def spy(*args, **kwargs):
            recorder["env"] = os.environ.get("SEGFACET_BACKEND")
            return original(*args, **kwargs)

        monkeypatch.setattr(mod, "evaluate_cohort", spy)
    elif sub == "build-reference":
        import segfacet.reference.artifact as mod

        original = mod.build_reference

        def spy(*args, **kwargs):
            recorder["env"] = os.environ.get("SEGFACET_BACKEND")
            return original(*args, **kwargs)

        monkeypatch.setattr(mod, "build_reference", spy)
    else:
        raise AssertionError(sub)


def _backend_action(sub_name):
    """Introspect ``_build_parser()`` for *sub_name*'s ``--backend`` action."""
    parser = _build_parser()
    subparsers_action = next(
        a for a in parser._actions if isinstance(a, argparse._SubParsersAction)
    )
    subparser = subparsers_action.choices[sub_name]
    return next(a for a in subparser._actions if a.dest == "backend")


# =========================================================================== #
# AC1  --backend cpu|gpu|auto present on all three subcommands
# =========================================================================== #


@pytest.mark.parametrize("sub", SUBCOMMANDS)
def test_ac1_backend_flag_choices_and_default(sub):
    action = _backend_action(sub)
    assert action.choices == ["cpu", "gpu", "auto"]
    assert action.default is None


# =========================================================================== #
# AC2  Invalid --backend token is a usage error
# =========================================================================== #


@pytest.mark.parametrize("sub", SUBCOMMANDS)
def test_ac2_invalid_backend_token_is_usage_error(sub):
    argv = _PLACEHOLDER_ARGV[sub] + ["--backend", "turbo"]
    with pytest.raises(SystemExit) as excinfo:
        main(argv)
    assert excinfo.value.code == 2


# =========================================================================== #
# AC3  Explicit --backend is eagerly validated/resolved via get_backend
# =========================================================================== #


@pytest.mark.parametrize("sub", SUBCOMMANDS)
def test_ac3_backend_flag_eagerly_resolves_via_get_backend(sub, tmp_path, monkeypatch):
    import segfacet.backend as backend_mod

    real_get_backend = backend_mod.get_backend
    calls = []

    def spy(override=None):
        calls.append(override)
        # Force CPU regardless of the recorded override so downstream
        # auto-resolution (item 072) also succeeds on this CuPy-absent host.
        return real_get_backend(override="cpu")

    monkeypatch.setattr(backend_mod, "get_backend", spy)

    argv, _out_target = _build_argv(sub, tmp_path, extra=["--backend", "cpu"])
    main(argv)

    assert "cpu" in calls


# =========================================================================== #
# AC4  Explicit --backend selects the backend via SEGFACET_BACKEND for the
#      unmodified compute entry point
# =========================================================================== #


@pytest.mark.parametrize("sub", SUBCOMMANDS)
def test_ac4_backend_flag_sets_env_seen_by_compute_entry(sub, tmp_path, monkeypatch):
    recorder = {}
    _install_compute_spy(sub, monkeypatch, recorder)

    argv, _out_target = _build_argv(sub, tmp_path, extra=["--backend", "cpu"])
    main(argv)

    assert recorder["env"] == "cpu"


# =========================================================================== #
# AC5  Forcing GPU without CuPy fails cleanly (Error + exit 1, no output)
# =========================================================================== #


@pytest.mark.parametrize("sub", SUBCOMMANDS)
def test_ac5_forcing_gpu_without_cupy_fails_cleanly(sub, tmp_path, capsys):
    if cupy_available():
        pytest.skip("This test targets a CuPy-absent host only.")

    argv, out_target = _build_argv(sub, tmp_path, extra=["--backend", "gpu"])
    code = main(argv)
    captured = capsys.readouterr()

    assert code == 1
    assert captured.err.startswith("Error:")
    assert captured.err.strip()
    assert "Traceback" not in captured.err
    for written in _expected_outputs(sub, out_target):
        assert not written.exists()


# =========================================================================== #
# AC6  Flag omitted + SEGFACET_BACKEND unset -> env untouched, no behaviour change
# =========================================================================== #


def test_ac6_backend_omitted_env_unset_no_behaviour_change(tmp_path, monkeypatch):
    monkeypatch.delenv("SEGFACET_BACKEND", raising=False)
    recorder = {}
    _install_compute_spy("run", monkeypatch, recorder)

    argv, out_target = _build_argv("run", tmp_path)
    main(argv)

    assert recorder["env"] is None
    assert (out_target / "segfacet_report.json").exists()
    assert (out_target / "segfacet_report.txt").exists()
    assert "SEGFACET_BACKEND" not in os.environ


# =========================================================================== #
# AC7  Flag omitted + ambient SEGFACET_BACKEND set -> ambient value governs
# =========================================================================== #


def test_ac7_backend_omitted_ambient_env_governs(tmp_path, monkeypatch):
    monkeypatch.setenv("SEGFACET_BACKEND", "cpu")
    recorder = {}
    _install_compute_spy("run", monkeypatch, recorder)

    argv, out_target = _build_argv("run", tmp_path)
    main(argv)

    assert recorder["env"] == "cpu"
    assert os.environ.get("SEGFACET_BACKEND") == "cpu"
    assert (out_target / "segfacet_report.json").exists()


# =========================================================================== #
# AC8  End-to-end CPU run needs zero GPU dependency
# =========================================================================== #


def test_ac8_end_to_end_cpu_run_needs_zero_gpu_dependency(tmp_path):
    if cupy_available():
        # On a CuPy-present host cupy is imported by sibling GPU tests in the same
        # process, so the "CPU run imports no cupy" invariant can't be observed
        # here; it is verified on the CuPy-absent baseline/CI host.
        pytest.skip("This test targets a CuPy-absent host only.")

    argv, out_target = _build_argv("run", tmp_path, extra=["--backend", "cpu"])
    main(argv)

    assert (out_target / "segfacet_report.json").exists()
    assert (out_target / "segfacet_report.txt").exists()
    assert "cupy" not in sys.modules


# =========================================================================== #
# AC13  No new core dependency; CPU-only install unaffected
# =========================================================================== #


def _load_pyproject():
    try:
        import tomllib  # Python 3.11+
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef]
    with open("pyproject.toml", "rb") as f:
        return tomllib.load(f)


def test_ac13_no_new_core_dependency():
    data = _load_pyproject()
    core_deps = " ".join(data["project"].get("dependencies", [])).lower()
    assert "cupy" not in core_deps
    assert "cucim" not in core_deps


# =========================================================================== #
# AC14  Existing CLI behaviour is unchanged when the flag is absent
# =========================================================================== #


def test_ac14_existing_run_cli_behaviour_unchanged_without_backend_flag(tmp_path):
    """Two independent invocations omitting --backend on the same inputs
    still produce byte-identical segfacet_report.json and matching exit codes --
    the new optional, None-default flag introduces no behavioural change to
    the pre-existing unflagged path (regression guard). The pre-existing
    run/evaluate/build-reference CLI test modules themselves are left
    unmodified by this item."""
    scan_path, seg_path = _run_files(tmp_path)
    out_a = tmp_path / "out_a"
    out_b = tmp_path / "out_b"

    code_a = main(
        ["run", "--scan", str(scan_path), "--seg", str(seg_path), "--out", str(out_a)]
    )
    code_b = main(
        ["run", "--scan", str(scan_path), "--seg", str(seg_path), "--out", str(out_b)]
    )

    assert code_a == code_b
    text_a = (out_a / "segfacet_report.json").read_text(encoding="utf-8")
    text_b = (out_b / "segfacet_report.json").read_text(encoding="utf-8")
    assert text_a == text_b


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_env_hermeticity_after_explicit_backend_selection(tmp_path, monkeypatch):
    """A11: the process-scoped selection ``--backend`` makes does not outlive a
    ``monkeypatch`` context that recorded the variable's prior value.

    Both ``setenv`` calls are load-bearing. A context can only undo what it
    recorded, and recording requires the name to be present -- so pinning the
    ambient value to ``auto`` first is what gives the context something to
    restore, and what makes this one assertion rather than a choice between
    two. The earlier version instead deleted the variable and read its
    pre-state off the inherited environment, which decided the outcome by
    whichever sibling test the runner had scheduled first (see
    ``_restore_backend_env`` above).
    """
    monkeypatch.setenv("SEGFACET_BACKEND", "auto")

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("SEGFACET_BACKEND", "auto")
        argv, _out_target = _build_argv("run", tmp_path, extra=["--backend", "cpu"])
        main(argv)
        assert os.environ.get("SEGFACET_BACKEND") == "cpu"

    assert os.environ.get("SEGFACET_BACKEND") == "auto"


def test_adv_explicit_backend_auto_overrides_ambient_cpu(tmp_path, monkeypatch):
    """A3: an explicit --backend auto overrides a preset ambient
    SEGFACET_BACKEND=cpu -- the compute path observes "auto" (which resolves to
    CPU on this host), proving the flag's precedence over the ambient env."""
    monkeypatch.setenv("SEGFACET_BACKEND", "cpu")
    recorder = {}
    _install_compute_spy("run", monkeypatch, recorder)

    argv, out_target = _build_argv("run", tmp_path, extra=["--backend", "auto"])
    main(argv)

    assert recorder["env"] == "auto"
    assert os.environ.get("SEGFACET_BACKEND") == "auto"
    assert (out_target / "segfacet_report.json").exists()


def test_adv_gpu_force_fails_before_any_input_loaded(tmp_path):
    """AC5's guard-before-GPU-selection: --backend gpu on this CuPy-absent
    host must fail at the eager get_backend step before --scan/--seg are
    ever loaded -- the --out directory itself must never even be created."""
    if cupy_available():
        pytest.skip("This test targets a CuPy-absent host only.")

    scan_path, seg_path = _run_files(tmp_path)
    out_dir = tmp_path / "out"

    code = main(
        [
            "run", "--scan", str(scan_path), "--seg", str(seg_path),
            "--out", str(out_dir), "--backend", "gpu",
        ]
    )

    assert code == 1
    assert not out_dir.exists()


@pytest.mark.parametrize("sub", SUBCOMMANDS)
def test_adv_bad_ambient_env_flag_omitted_fails_cleanly(sub, tmp_path, monkeypatch, capsys):
    """A4: a bad *ambient* SEGFACET_BACKEND (gpu, CuPy absent) with --backend
    omitted must surface as a clean Error: + exit 1 (eager validation), not a
    mid-pipeline traceback, and must write no output."""
    if cupy_available():
        pytest.skip("This test targets a CuPy-absent host only.")

    monkeypatch.setenv("SEGFACET_BACKEND", "gpu")
    argv, out_target = _build_argv(sub, tmp_path)

    code = main(argv)
    captured = capsys.readouterr()

    assert code == 1
    assert captured.err.startswith("Error:")
    assert "Traceback" not in captured.err
    for written in _expected_outputs(sub, out_target):
        assert not written.exists()
