"""CPU-vs-GPU verdict-equivalence test suite (item 073).

**Mechanism (A1).** Item 072 threads ``backend: Optional[Backend] = None``
through the Stage-2/3 feature functions (``compute_label_geometry``,
``compute_components``, ``compute_centroid``, ``compute_edt_centroids``, the
fragmentation/spline/spline_offset ports). ``None`` auto-resolves via
``segfacet.backend.get_backend()`` **at call time**, honouring the
``SEGFACET_BACKEND`` environment variable (item 071). ``run_qc ->
extract_feature_record`` calls those functions with **no** ``backend``
argument, so setting ``SEGFACET_BACKEND=cpu`` / ``SEGFACET_BACKEND=gpu`` in the
environment (via ``monkeypatch.setenv``/``delenv``) selects the backend for a
whole ``run_qc`` call with **no change to ``pipeline.py`` or ``cli.py``**.
There is no CLI ``--backend`` flag or ``run_qc`` parameter here (that is item
075's job) -- the env var is the only seam this suite drives.

**Exact-verdict / tolerant-feature policy (A2).** The QC *verdict* --
``verdict.overall.label`` plus the full findings set compared as
``(rule_id, sorted(labels), severity)`` -- must be **bit-identical** between
backends. Only the numeric ``features`` block's **float** leaves are compared
within tolerance; every categorical/string/integer-count leaf must match
**exactly**. A backend difference that flips a verdict, changes a fired rule,
or changes an offending-label set is a failure, never tolerated drift.

**Documented tolerance (A3).** Float feature-leaf comparison uses
``numpy.isclose(cpu, gpu, rtol=1e-5, atol=1e-6)`` -- see ``RTOL``/``ATOL``
below.

**Partial-GPU-coverage reality (A4).** Item 072 ports only a subset of the
compute (geometry, connected components, centroid/EDT, fragmentation) to
``Backend.xp``/``Backend.ndimage``; the spline steps and the un-ported
case-level extractors (``relationships``, ``overlaps``, ``orientation``,
``curvature``, ``consistency``) always run on CPU/SciPy, even under a GPU
backend. Equivalence is therefore expected to hold easily for much of the
block (it never touched the GPU); the tolerance exists for the genuinely
GPU-computed leaves. This is a documented reality of the current port, not a
gap this suite closes.

**GPU-less-host skip behaviour.** This dev/CI host has no GPU and no CuPy.
The always-run assertions (AC1-AC6) exercise the CPU path and the
comparison-helper machinery unconditionally; every GPU-*executing* assertion
(AC7-AC9) is gated behind ``requires_cupy`` and skips cleanly (never fails,
never vacuously passes) here, mirroring item 069's Docker-gated precedent.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy
import pytest

from segfacet.aggregate import CaseResult
from segfacet.backend import ENV_VAR, FacetBackendError, cupy_available
from segfacet.config import bundled_default_config
from segfacet.heuristics import Finding
from segfacet.pipeline import extract_feature_record, run_qc
from segfacet.synth.corpus import load_manifest
from segfacet.synth.golden import canonical_json
from segfacet.synth.regression import loaded_seg_image
from segfacet.verdict import Reason, Severity, Verdict

from synthetic import anisotropic_case, empty_case, labelled_blocks_case, make_labelmap

# --------------------------------------------------------------------------- #
# Shared GPU gate (item 069 precedent)
# --------------------------------------------------------------------------- #

requires_cupy = pytest.mark.skipif(
    not cupy_available(), reason="CuPy/GPU not available"
)

# Documented numeric tolerance for float feature leaves (A3).
RTOL = 1e-5
ATOL = 1e-6

_MANIFEST = load_manifest()
_CASES = _MANIFEST["cases"]
_CASE_IDS = [c["case_id"] for c in _CASES]


def _case(case_id: str) -> dict:
    for c in _CASES:
        if c["case_id"] == case_id:
            return c
    raise AssertionError(f"case_id {case_id!r} not found in the committed manifest")


# --------------------------------------------------------------------------- #
# Comparison helpers (the test-side deliverable)
# --------------------------------------------------------------------------- #


def verdict_signature(case_result: CaseResult) -> tuple:
    """Order-insensitive, hashable, exactly-comparable categorical signature.

    ``(overall_label, frozenset of (rule_id, sorted(labels), severity))``.
    """
    findings_dicts = [fd.to_dict() for fd in case_result.findings]
    signature = frozenset(
        (f["rule_id"], tuple(sorted(f["labels"])), f["severity"])
        for f in findings_dicts
    )
    return (case_result.verdict.overall.label, signature)


def feature_leaves_close(cpu_block, gpu_block, *, rtol: float, atol: float) -> bool:
    """Walk two nested dict/list structures in lockstep.

    Requires identical structure/keys; compares ``float`` leaves with
    ``numpy.isclose(rtol=rtol, atol=atol)`` and all other leaves (str/int/
    bool/None) with ``==``. Returns ``False`` on any structural mismatch or
    out-of-tolerance leaf.
    """
    cpu_is_dict = isinstance(cpu_block, dict)
    gpu_is_dict = isinstance(gpu_block, dict)
    if cpu_is_dict != gpu_is_dict:
        return False
    if cpu_is_dict:
        if set(cpu_block.keys()) != set(gpu_block.keys()):
            return False
        return all(
            feature_leaves_close(cpu_block[k], gpu_block[k], rtol=rtol, atol=atol)
            for k in cpu_block
        )

    cpu_is_seq = isinstance(cpu_block, (list, tuple))
    gpu_is_seq = isinstance(gpu_block, (list, tuple))
    if cpu_is_seq != gpu_is_seq:
        return False
    if cpu_is_seq:
        if len(cpu_block) != len(gpu_block):
            return False
        return all(
            feature_leaves_close(a, b, rtol=rtol, atol=atol)
            for a, b in zip(cpu_block, gpu_block)
        )

    # bool before float/int: bool is an int subclass but must match exactly.
    if isinstance(cpu_block, bool) or isinstance(gpu_block, bool):
        return cpu_block == gpu_block

    if isinstance(cpu_block, float) and isinstance(gpu_block, float):
        return bool(numpy.isclose(cpu_block, gpu_block, rtol=rtol, atol=atol))

    return cpu_block == gpu_block


def run_under_backend(seg_img, cfg, token, monkeypatch):
    """Select *token* via ``SEGFACET_BACKEND`` and run the full pipeline.

    ``token=None`` clears the env var (auto-resolution); otherwise it is set
    verbatim (``"cpu"``/``"gpu"``). Returns ``run_qc``'s
    ``(CaseResult, features_block)`` tuple unchanged.
    """
    if token is None:
        monkeypatch.delenv(ENV_VAR, raising=False)
    else:
        monkeypatch.setenv(ENV_VAR, token)
    return run_qc(seg_img, cfg)


def _single_label_seg_img():
    """A degenerate 1-label map (Stage 2 only, no ``stage3``)."""
    return make_labelmap(blocks={1: ((2, 6), (2, 6), (2, 6))})


# =========================================================================== #
# AC1  Suite module present and collectable GPU-free
# =========================================================================== #


def test_ac1_module_present_and_collectable_gpu_free():
    module_path = Path(__file__).resolve()
    assert module_path.is_file(), "tests/test_073_verdict_equivalence.py must exist"

    import segfacet.backend  # noqa: F401 -- must import cleanly with no cupy installed

    assert hasattr(segfacet.backend, "cupy_available")


# =========================================================================== #
# AC2  CPU-backend full-pipeline verdict is reproducible
# =========================================================================== #


@pytest.mark.parametrize("case", _CASES, ids=_CASE_IDS)
def test_ac2_cpu_backend_verdict_reproducible(case, monkeypatch):
    cfg = bundled_default_config()
    seg_img = loaded_seg_image(case)

    result_a, _ = run_under_backend(seg_img, cfg, "cpu", monkeypatch)
    result_b, _ = run_under_backend(seg_img, cfg, "cpu", monkeypatch)

    assert verdict_signature(result_a) == verdict_signature(result_b)


# =========================================================================== #
# AC3  CPU-backend feature block is byte-deterministic
# =========================================================================== #


def test_ac3_cpu_backend_feature_block_byte_deterministic(monkeypatch):
    case = _case("clean_control")
    cfg = bundled_default_config()
    seg_img = loaded_seg_image(case)

    monkeypatch.setenv(ENV_VAR, "cpu")
    block_a = extract_feature_record(seg_img, cfg)
    block_b = extract_feature_record(seg_img, cfg)

    assert canonical_json(block_a) == canonical_json(block_b)


# =========================================================================== #
# AC4  Auto-resolved default equals explicit CPU on this CuPy-absent host
# =========================================================================== #


def test_ac4_auto_resolved_default_equals_explicit_cpu(monkeypatch):
    case = _case("clean_control")
    cfg = bundled_default_config()
    seg_img = loaded_seg_image(case)

    result_unset, _ = run_under_backend(seg_img, cfg, None, monkeypatch)
    result_cpu, _ = run_under_backend(seg_img, cfg, "cpu", monkeypatch)

    assert verdict_signature(result_unset) == verdict_signature(result_cpu)


# =========================================================================== #
# AC5  The equivalence comparison helper is non-vacuous
# =========================================================================== #


def test_ac5_comparison_helpers_are_non_vacuous():
    # -- verdict_signature: two deliberately different verdict signatures --
    pass_verdict = Verdict.build(reasons=[], per_label={})
    result_pass = CaseResult(verdict=pass_verdict, findings=())

    fail_verdict = Verdict.build(
        reasons=[Reason(message="synthetic failure", severity=Severity.FAIL)],
        per_label={},
    )
    fail_finding = Finding(
        rule_id="synthetic_rule",
        severity=Severity.FAIL,
        reason="synthetic failure",
        labels=frozenset({1}),
    )
    result_fail = CaseResult(verdict=fail_verdict, findings=(fail_finding,))

    assert verdict_signature(result_pass) != verdict_signature(result_fail)

    # Same overall label but a different fired rule set must also differ.
    other_finding = Finding(
        rule_id="a_different_rule",
        severity=Severity.FAIL,
        reason="a different synthetic failure",
        labels=frozenset({2}),
    )
    result_fail_other = CaseResult(verdict=fail_verdict, findings=(other_finding,))
    assert verdict_signature(result_fail) != verdict_signature(result_fail_other)

    # -- feature_leaves_close: a float leaf perturbed well beyond tolerance --
    # np.isclose's effective tolerance at value=10.0 is atol + rtol*|value| =
    # 1e-6 + 1e-5*10 ~= 1.01e-4, so the offset must clear that margin (not just
    # 10*atol, which is dwarfed by the rtol*|value| term at this magnitude).
    base_value = 10.0
    offset = 2 * (ATOL + RTOL * abs(base_value))
    cpu_block = {"per_label": {"1": {"volume_mm3": base_value, "level_name": "L1"}}}
    gpu_block = {
        "per_label": {"1": {"volume_mm3": base_value + offset, "level_name": "L1"}}
    }
    assert feature_leaves_close(cpu_block, gpu_block, rtol=RTOL, atol=ATOL) is False

    # A structural mismatch (missing key) must also be caught.
    gpu_block_missing_key = {"per_label": {"1": {"volume_mm3": 10.0}}}
    assert (
        feature_leaves_close(cpu_block, gpu_block_missing_key, rtol=RTOL, atol=ATOL)
        is False
    )


# =========================================================================== #
# AC6  The GPU gate is a genuine skip marker
# =========================================================================== #


def test_ac6_gpu_gate_is_genuine_skip_marker():
    """Mirrors ``test_069_container_smoke.py``'s ``test_ac2_...``: the marker
    is a real ``skipif`` with a ``bool`` condition (never ``xfail``, never an
    unconditional pass), and on this CuPy-absent host it evaluates truthy."""
    if cupy_available():
        pytest.skip("This test targets a CuPy-absent host only.")
    assert requires_cupy.mark.name == "skipif"
    assert isinstance(requires_cupy.mark.args[0], bool)
    assert requires_cupy.mark.args[0] is True


# =========================================================================== #
# AC7  GPU vs CPU verdicts are identical (gated)
# =========================================================================== #


@requires_cupy
@pytest.mark.parametrize("case", _CASES, ids=_CASE_IDS)
def test_ac7_gpu_vs_cpu_verdict_identical(case, monkeypatch):
    cfg = bundled_default_config()
    seg_img = loaded_seg_image(case)

    cpu_result, _ = run_under_backend(seg_img, cfg, "cpu", monkeypatch)
    gpu_result, _ = run_under_backend(seg_img, cfg, "gpu", monkeypatch)

    assert verdict_signature(cpu_result) == verdict_signature(gpu_result)


# =========================================================================== #
# AC8  GPU vs CPU feature values agree within documented tolerance (gated)
# =========================================================================== #


@requires_cupy
@pytest.mark.parametrize("case", _CASES, ids=_CASE_IDS)
def test_ac8_gpu_vs_cpu_feature_values_within_tolerance(case, monkeypatch):
    cfg = bundled_default_config()
    seg_img = loaded_seg_image(case)

    _, cpu_block = run_under_backend(seg_img, cfg, "cpu", monkeypatch)
    _, gpu_block = run_under_backend(seg_img, cfg, "gpu", monkeypatch)

    assert feature_leaves_close(cpu_block, gpu_block, rtol=RTOL, atol=ATOL)


# =========================================================================== #
# AC9  GPU vs CPU equivalence on the Stage-0 tiny + anisotropic fixtures (gated)
# =========================================================================== #


@requires_cupy
@pytest.mark.parametrize(
    "build_case",
    [labelled_blocks_case, anisotropic_case],
    ids=["labelled_blocks", "anisotropic"],
)
def test_ac9_gpu_vs_cpu_equivalence_on_stage0_fixtures(build_case, monkeypatch):
    cfg = bundled_default_config()
    seg_img = build_case().seg_img

    cpu_result, cpu_block = run_under_backend(seg_img, cfg, "cpu", monkeypatch)
    gpu_result, gpu_block = run_under_backend(seg_img, cfg, "gpu", monkeypatch)

    assert verdict_signature(cpu_result) == verdict_signature(gpu_result)
    assert feature_leaves_close(cpu_block, gpu_block, rtol=RTOL, atol=ATOL)


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_edge_empty_and_single_label_maps_equal_verdict_signature_under_cpu(
    monkeypatch,
):
    """Degenerate 0- and 1-label maps (no ``relationships``, no ``stage3``)
    route through the abstraction without divergence on repeated CPU runs."""
    cfg = bundled_default_config()
    for seg_img in (empty_case().seg_img, _single_label_seg_img()):
        result_a, _ = run_under_backend(seg_img, cfg, "cpu", monkeypatch)
        result_b, _ = run_under_backend(seg_img, cfg, "cpu", monkeypatch)
        assert verdict_signature(result_a) == verdict_signature(result_b)


def test_edge_env_hermeticity_after_backend_selection():
    """After a ``SEGFACET_BACKEND`` selection made via a monkeypatch context
    exits, the ambient ``os.environ`` state is restored -- no backend
    selection leaks into another test or the wider suite (A7)."""
    original_present = ENV_VAR in os.environ
    original_value = os.environ.get(ENV_VAR)

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv(ENV_VAR, "cpu")
        assert os.environ[ENV_VAR] == "cpu"

    if original_present:
        assert os.environ.get(ENV_VAR) == original_value
    else:
        assert ENV_VAR not in os.environ


def test_edge_gpu_selection_without_cupy_raises_backend_error(monkeypatch):
    """Sanity check underpinning A5: on this CuPy-absent host, actually
    setting ``SEGFACET_BACKEND=gpu`` and calling ``run_qc`` raises
    ``FacetBackendError`` rather than silently running -- exactly why
    AC7-AC9 must be gated by ``@requires_cupy`` *before* ever setting
    ``SEGFACET_BACKEND=gpu``, so a CuPy-absent host skips instead of erroring."""
    if cupy_available():
        pytest.skip("This sanity check targets a CuPy-absent host only.")

    cfg = bundled_default_config()
    seg_img = labelled_blocks_case().seg_img

    monkeypatch.setenv(ENV_VAR, "gpu")
    with pytest.raises(FacetBackendError):
        run_qc(seg_img, cfg)
