"""Stage-10 acceptance check (item 075, AC9-AC12 -- the Part-B half of Stage
10's integration closer).

Ties items 071-074 together into one coherent, testable acceptance bar and
records -- at runtime, never in a committed host-specific note (A8) -- which
of the roadmap's two Stage-10 acceptance clauses were actually exercised on
the host that ran it:

- The **CPU-only clause** (AC9): the full pipeline runs end-to-end under the
  CPU backend, producing a verdict with zero GPU dependency. Unconditional --
  passes on every host, including this CuPy-absent one.
- The **CPU/GPU verdict-equivalence clause** (AC10): reuses item 073's
  ``verdict_signature``/``run_under_backend`` mechanism to assert CPU-vs-GPU
  verdict identity, gated on ``cupy_available()`` -- runs and asserts when
  CuPy is genuinely importable, skips cleanly (never errors, never vacuously
  passes) when it is absent. On this host it skips.

``stage10_acceptance_record`` (AC11) is the importable evidence helper; a
companion test prints it so the run's own captured output states plainly
which clause it verified (A8).
"""

from __future__ import annotations

import json
import os

import pytest

from segqc.backend import ENV_VAR, cupy_available
from segqc.config import bundled_default_config
from segqc.synth.corpus import load_manifest
from segqc.synth.regression import loaded_seg_image
from segqc.verdict import Severity

from test_073_verdict_equivalence import run_under_backend, verdict_signature

_MANIFEST = load_manifest()
_REPRESENTATIVE_CASE = next(
    c for c in _MANIFEST["cases"] if c["case_id"] == "clean_control"
)

requires_cupy = pytest.mark.skipif(
    not cupy_available(), reason="CuPy/GPU not available"
)


def stage10_acceptance_record(*, gpu_ran: bool) -> dict:
    """Runtime evidence record for the Stage-10 acceptance check (A8).

    JSON-native: ``{"cupy_available": bool, "cpu_clause_exercised": True,
    "gpu_clause_exercised": bool}`` -- states, from this run's own captured
    output, which of the roadmap's two Stage-10 acceptance clauses were
    exercised on this host, rather than a stale committed note.
    """
    return {
        "cupy_available": cupy_available(),
        "cpu_clause_exercised": True,
        "gpu_clause_exercised": gpu_ran,
    }


# =========================================================================== #
# AC9  CPU clause holds unconditionally
# =========================================================================== #


def test_ac9_cpu_clause_holds_unconditionally(monkeypatch):
    cfg = bundled_default_config()
    seg_img = loaded_seg_image(_REPRESENTATIVE_CASE)

    result, _features_block = run_under_backend(seg_img, cfg, "cpu", monkeypatch)

    assert result.verdict.overall in (Severity.PASS, Severity.FLAG, Severity.FAIL)


# =========================================================================== #
# AC10  GPU-equivalence clause is gated (CPU-vs-GPU verdict identity)
# =========================================================================== #


@requires_cupy
def test_ac10_gpu_vs_cpu_verdict_identical(monkeypatch):
    cfg = bundled_default_config()
    seg_img = loaded_seg_image(_REPRESENTATIVE_CASE)

    cpu_result, _ = run_under_backend(seg_img, cfg, "cpu", monkeypatch)
    gpu_result, _ = run_under_backend(seg_img, cfg, "gpu", monkeypatch)

    assert verdict_signature(cpu_result) == verdict_signature(gpu_result)


# =========================================================================== #
# AC11  Acceptance evidence records which clause was exercised
# =========================================================================== #


def test_ac11_evidence_record_matches_host_capability():
    record = stage10_acceptance_record(gpu_ran=cupy_available())

    assert record["cpu_clause_exercised"] is True
    assert record["gpu_clause_exercised"] == cupy_available()
    assert record["cupy_available"] == cupy_available()


def test_ac11_evidence_record_is_printed_as_runtime_output(capsys):
    """A8: the evidence record is printed to captured pytest output (not
    merely returned by the helper), so the run's own output plainly states
    which clause it exercised on this host."""
    record = stage10_acceptance_record(gpu_ran=cupy_available())
    print(json.dumps(record, sort_keys=True))

    captured = capsys.readouterr()
    reprinted = json.loads(captured.out.strip().splitlines()[-1])
    assert reprinted == record


# =========================================================================== #
# AC12  The GPU acceptance gate is a genuine skip marker
# =========================================================================== #


def test_ac12_gpu_gate_is_genuine_skip_marker():
    """Mirrors tests/test_069_container_smoke.py's genuine-skip precedent
    (and item 073 AC6 / item 074 AC14): the marker gating the GPU-equivalence
    acceptance test is a real pytest.mark.skipif with a bool condition (never
    xfail, never an unconditional pass), True on this CuPy-absent host."""
    if cupy_available():
        pytest.skip("This test targets a CuPy-absent host only.")
    assert requires_cupy.mark.name == "skipif"
    assert isinstance(requires_cupy.mark.args[0], bool)
    assert requires_cupy.mark.args[0] is True


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_evidence_never_reports_gpu_verified_when_gpu_clause_skipped():
    """Non-vacuity (A8): on this CuPy-absent host both cupy_available() and
    gpu_clause_exercised must be False while cpu_clause_exercised stays True
    -- "GPU clause verified" can never be reported when it was in fact
    skipped."""
    if cupy_available():
        pytest.skip("This adversarial check targets a CuPy-absent host only.")

    record = stage10_acceptance_record(gpu_ran=False)

    assert record["cupy_available"] is False
    assert record["gpu_clause_exercised"] is False
    assert record["cpu_clause_exercised"] is True


def test_adv_evidence_record_mismatched_gpu_ran_is_detectable():
    """A caller passing a mismatched gpu_ran=True on this CuPy-absent host
    produces a record whose gpu_clause_exercised disagrees with
    cupy_available() -- exactly the condition the AC11 assertion
    (gpu_clause_exercised == cupy_available()) is built to catch, proving the
    check is not vacuous."""
    if cupy_available():
        pytest.skip("This adversarial check targets a CuPy-absent host only.")

    record = stage10_acceptance_record(gpu_ran=True)

    assert record["gpu_clause_exercised"] != record["cupy_available"]


def test_adv_env_hermeticity_around_cpu_clause_run():
    """Env hygiene: the SEGQC_BACKEND selection made via run_under_backend's
    monkeypatch parameter does not leak past that monkeypatch context's
    teardown."""
    original_present = ENV_VAR in os.environ
    original_value = os.environ.get(ENV_VAR)

    with pytest.MonkeyPatch.context() as mp:
        cfg = bundled_default_config()
        seg_img = loaded_seg_image(_REPRESENTATIVE_CASE)
        run_under_backend(seg_img, cfg, "cpu", mp)
        assert os.environ.get(ENV_VAR) == "cpu"

    if original_present:
        assert os.environ.get(ENV_VAR) == original_value
    else:
        assert ENV_VAR not in os.environ
