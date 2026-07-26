"""CPU/GPU feature-extraction performance benchmark test suite (item 074).

Structural-correctness suite for ``segfacet.benchmark`` -- a lightweight,
deterministic-in-*scope* (not in timing) benchmark that times
``segfacet.pipeline.extract_feature_record`` per available backend
(``SEGFACET_BACKEND``-driven, item 071/072) and emits a schema-valid JSON report.

**No absolute-time assertions.** Per the item scope fence, this suite never
compares a timing value to a fixed second-count threshold -- only structural
correctness (schema, backend-set correctness, JSON round-trip, script entry
point, read-only fixture use, iteration-scope determinism) is asserted.

**GPU-less-host skip behaviour.** AC1-AC13 run and pass unconditionally on a
GPU-less host; AC14-AC15 are gated by the shared ``requires_cupy`` marker
(mirroring ``tests/test_069_container_smoke.py`` / ``tests/test_073_verdict_
equivalence.py``'s precedent) and skip cleanly here.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import numpy
import pytest

from segfacet.backend import ENV_VAR, cupy_available
from segfacet.config import bundled_default_config
from segfacet.synth.corpus import load_manifest
from segfacet.synth.regression import loaded_seg_image

REPO_ROOT = Path(__file__).resolve().parent.parent

# --------------------------------------------------------------------------- #
# Shared GPU gate (item 069/073 precedent)
# --------------------------------------------------------------------------- #

requires_cupy = pytest.mark.skipif(
    not cupy_available(), reason="CuPy/GPU not available"
)

_MANIFEST = load_manifest()
_CASES = _MANIFEST["cases"]


def _case(case_id: str) -> dict:
    for c in _CASES:
        if c["case_id"] == case_id:
            return c
    raise AssertionError(f"case_id {case_id!r} not found in the committed manifest")


def _n_labels(case: dict) -> int:
    seg_img = loaded_seg_image(case)
    data = seg_img.get_fdata()
    return int(numpy.unique(data[data != 0]).size)


def _first_multilabel_case() -> dict:
    for c in _CASES:
        if _n_labels(c) >= 2:
            return c
    raise AssertionError("no committed corpus case has >= 2 labels")


REQUIRED_TOP_KEYS = {
    "benchmark_version": str,
    "timed_unit": str,
    "iterations": int,
    "warmup": int,
    "cupy_available": bool,
    "fixture": dict,
    "backends": list,
}

REQUIRED_BACKEND_KEYS = {
    "name": str,
    "is_gpu": bool,
    "iterations": int,
    "warmup": int,
    "timings_s": list,
    "min_s": float,
    "mean_s": float,
    "median_s": float,
}


def _assert_schema_valid(report: dict) -> None:
    for key, typ in REQUIRED_TOP_KEYS.items():
        assert key in report, f"missing top-level key {key!r}"
        assert isinstance(report[key], typ), f"{key!r} is not a {typ}"
    for entry in report["backends"]:
        for key, typ in REQUIRED_BACKEND_KEYS.items():
            assert key in entry, f"missing backends[] key {key!r}"
            assert isinstance(entry[key], typ), f"{key!r} is not a {typ}"


def _cpu_entry(report: dict) -> dict:
    cpu_entries = [b for b in report["backends"] if b["name"] == "cpu"]
    assert len(cpu_entries) == 1
    return cpu_entries[0]


# =========================================================================== #
# AC1  Module imports GPU-free
# =========================================================================== #


def test_ac1_module_imports_gpu_free():
    import segfacet.benchmark  # noqa: F401 -- must import cleanly with no cupy installed

    # The module itself must not have imported cupy at module scope: check the
    # module's own namespace for a bound `cupy` name (a module-scope `import
    # cupy` would bind one), rather than sys.modules (which other test modules
    # may have already populated via unrelated stubs).
    assert "cupy" not in vars(segfacet.benchmark)


# =========================================================================== #
# AC2  run_benchmark returns a report and runs to completion
# =========================================================================== #


def test_ac2_run_benchmark_returns_dict_without_raising():
    from segfacet.benchmark import run_benchmark

    report = run_benchmark(iterations=2, warmup=1)
    assert isinstance(report, dict)


# =========================================================================== #
# AC3  Report carries the documented schema
# =========================================================================== #


def test_ac3_report_carries_documented_schema():
    from segfacet.benchmark import run_benchmark

    report = run_benchmark(iterations=2, warmup=1)
    _assert_schema_valid(report)
    assert report["timed_unit"] == "extract_feature_record"


# =========================================================================== #
# AC4  CPU backend entry always present
# =========================================================================== #


def test_ac4_exactly_one_cpu_entry_present():
    from segfacet.benchmark import run_benchmark

    report = run_benchmark(iterations=2, warmup=1)
    cpu_entries = [b for b in report["backends"] if b["name"] == "cpu"]
    assert len(cpu_entries) == 1
    assert cpu_entries[0]["is_gpu"] is False


# =========================================================================== #
# AC5  CPU timings are positive
# =========================================================================== #


def test_ac5_cpu_timings_are_positive():
    from segfacet.benchmark import run_benchmark

    report = run_benchmark(iterations=2, warmup=1)
    cpu = _cpu_entry(report)
    assert all(isinstance(t, float) and t > 0 for t in cpu["timings_s"])
    assert cpu["min_s"] > 0
    assert cpu["mean_s"] > 0
    assert cpu["median_s"] > 0


# =========================================================================== #
# AC6  Iteration scope is deterministic and honoured
# =========================================================================== #


def test_ac6_iteration_scope_honoured():
    from segfacet.benchmark import run_benchmark

    report = run_benchmark(iterations=3, warmup=1)
    cpu = _cpu_entry(report)
    assert len(cpu["timings_s"]) == 3
    assert report["iterations"] == 3
    assert report["warmup"] == 1
    assert cpu["iterations"] == 3


# =========================================================================== #
# AC7  GPU entry absent (not zero, not a crash) when CuPy is absent
# =========================================================================== #


def test_ac7_gpu_entry_absent_when_cupy_absent():
    from segfacet.benchmark import run_benchmark

    if cupy_available():
        pytest.skip("This assertion targets a CuPy-absent host only.")

    report = run_benchmark(iterations=2, warmup=1)
    assert report["cupy_available"] is False
    assert not any(b["name"] == "gpu" for b in report["backends"])


# =========================================================================== #
# AC8  Backends reported equal backends available
# =========================================================================== #


def test_ac8_backend_name_set_matches_availability():
    from segfacet.benchmark import run_benchmark

    report = run_benchmark(iterations=2, warmup=1)
    names = {b["name"] for b in report["backends"]}
    expected = {"cpu", "gpu"} if cupy_available() else {"cpu"}
    assert names == expected


# =========================================================================== #
# AC9  Report is JSON well-formed / round-trippable
# =========================================================================== #


def test_ac9_report_is_json_round_trippable():
    from segfacet.benchmark import run_benchmark

    report = run_benchmark(iterations=2, warmup=1)
    assert json.loads(json.dumps(report)) == report


# =========================================================================== #
# AC10  Script entry point writes a parseable JSON file
# =========================================================================== #


def test_ac10_main_writes_parseable_json_file(tmp_path):
    from segfacet.benchmark import main

    out_path = tmp_path / "r.json"
    rc = main(["--out", str(out_path), "--iterations", "2", "--warmup", "1"])

    assert rc == 0
    assert out_path.is_file()

    report = json.loads(out_path.read_text(encoding="utf-8"))
    _assert_schema_valid(report)
    assert _cpu_entry(report)["min_s"] > 0


# =========================================================================== #
# AC11  Fixture is reused, small, and recorded deterministically
# =========================================================================== #


def test_ac11_fixture_identifies_a_committed_corpus_case():
    from segfacet.benchmark import run_benchmark

    report = run_benchmark(iterations=2, warmup=1)
    fixture = report["fixture"]

    assert fixture["source"] == "corpus"
    assert isinstance(fixture["case_id"], str) and fixture["case_id"]
    assert fixture["n_labels"] >= 2

    case = _case(fixture["case_id"])
    seg_img = loaded_seg_image(case)
    assert fixture["shape"] == list(seg_img.shape)
    assert fixture["spacing_mm"] == [
        float(z) for z in seg_img.header.get_zooms()[:3]
    ]


def test_ac11_no_new_binary_fixture_added_by_this_item():
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=A", "main...HEAD"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        pytest.skip("git diff against main unavailable in this environment")

    added = [line for line in result.stdout.splitlines() if line.strip()]
    assert not any(f.endswith((".nii", ".nii.gz")) for f in added), added


# =========================================================================== #
# AC12  Benchmark is read-only
# =========================================================================== #


def test_ac12_benchmark_does_not_mutate_fixture_seg_image():
    from segfacet.benchmark import run_benchmark

    case = _first_multilabel_case()
    before = loaded_seg_image(case).get_fdata().copy()

    run_benchmark(case_id=case["case_id"], iterations=2, warmup=1)

    after = loaded_seg_image(case).get_fdata()
    assert numpy.array_equal(before, after)


# =========================================================================== #
# AC13  No new core dependency
# =========================================================================== #


def _load_pyproject():
    try:
        import tomllib  # Python 3.11+
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef]
    with open(REPO_ROOT / "pyproject.toml", "rb") as f:
        return tomllib.load(f)


def test_ac13_core_dependencies_unchanged_no_cupy():
    expected_deps = {
        "numpy>=1.26,<3",
        "scipy>=1.7",
        "scikit-image>=0.19",
        "nibabel>=4.0",
        "PyYAML>=5.4",
        "jsonschema>=3.2",
        "tptbox==0.7.5",
    }
    data = _load_pyproject()
    core_deps = set(data["project"].get("dependencies", []))

    assert core_deps == expected_deps
    assert "cupy" not in " ".join(core_deps).lower()


# =========================================================================== #
# AC14  GPU-timing test is genuinely CuPy-gated (real skip, not vacuous)
# =========================================================================== #


def test_ac14_gpu_gate_is_genuine_skip_marker():
    """Mirrors ``test_069_container_smoke.py`` / ``test_073_verdict_
    equivalence.py``: the marker is a real ``skipif`` with a ``bool``
    condition (never ``xfail``, never an unconditional pass), and on this
    CuPy-absent host it evaluates truthy."""
    if cupy_available():
        pytest.skip("This test targets a CuPy-absent host only.")
    assert requires_cupy.mark.name == "skipif"
    assert isinstance(requires_cupy.mark.args[0], bool)
    assert requires_cupy.mark.args[0] is True


# =========================================================================== #
# AC15  GPU entry present and positive when CuPy is available (gated)
# =========================================================================== #


@requires_cupy
def test_ac15_gpu_entry_present_and_positive_when_cupy_available():
    from segfacet.benchmark import run_benchmark

    report = run_benchmark(iterations=2, warmup=1)
    gpu_entries = [b for b in report["backends"] if b["name"] == "gpu"]
    assert len(gpu_entries) == 1
    gpu = gpu_entries[0]
    assert gpu["is_gpu"] is True
    assert len(gpu["timings_s"]) == 2
    assert all(t > 0 for t in gpu["timings_s"])
    assert report["cupy_available"] is True


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_edge_env_var_hygiene_no_leak_after_run_benchmark():
    """After run_benchmark returns, SEGFACET_BACKEND must not be left set in
    os.environ -- a leaked selection would silently affect any subsequent
    test/module that reads the env var."""
    original_present = ENV_VAR in os.environ
    original_value = os.environ.get(ENV_VAR)

    from segfacet.benchmark import run_benchmark

    run_benchmark(iterations=2, warmup=1)

    if original_present:
        assert os.environ.get(ENV_VAR) == original_value
    else:
        assert ENV_VAR not in os.environ


def test_edge_iterations_one_boundary_min_mean_median_equal_single_sample():
    from segfacet.benchmark import run_benchmark

    report = run_benchmark(iterations=1, warmup=1)
    cpu = _cpu_entry(report)

    assert len(cpu["timings_s"]) == 1
    only_sample = cpu["timings_s"][0]
    assert cpu["min_s"] == only_sample
    assert cpu["mean_s"] == only_sample
    assert cpu["median_s"] == only_sample


def test_edge_explicit_case_selects_exactly_that_case():
    from segfacet.benchmark import run_benchmark

    case = _first_multilabel_case()
    report = run_benchmark(case_id=case["case_id"], iterations=2, warmup=1)

    assert report["fixture"]["case_id"] == case["case_id"]


def test_edge_gpu_gate_non_vacuous_skip_condition_is_not_hardcoded_true():
    """The truthy skip condition on this host is derived from a live
    cupy_available() probe, not a hardcoded literal -- so a GPU-executing
    assertion can never be silently reported "passed" when it was in fact
    skipped."""
    assert requires_cupy.mark.args[0] == (not cupy_available())


def test_edge_scope_determinism_across_repeated_calls():
    """Two run_benchmark(iterations=2) calls yield identical structure /
    field-sets and identical fixture metadata; only the timings themselves
    (and their derived stats) are allowed to differ."""
    from segfacet.benchmark import run_benchmark

    report_a = run_benchmark(iterations=2, warmup=1)
    report_b = run_benchmark(iterations=2, warmup=1)

    assert set(report_a.keys()) == set(report_b.keys())
    assert report_a["fixture"] == report_b["fixture"]

    names_a = sorted(b["name"] for b in report_a["backends"])
    names_b = sorted(b["name"] for b in report_b["backends"])
    assert names_a == names_b

    for entry_a, entry_b in zip(
        sorted(report_a["backends"], key=lambda b: b["name"]),
        sorted(report_b["backends"], key=lambda b: b["name"]),
    ):
        assert set(entry_a.keys()) == set(entry_b.keys())
        assert entry_a["iterations"] == entry_b["iterations"]
        assert entry_a["warmup"] == entry_b["warmup"]
        assert len(entry_a["timings_s"]) == len(entry_b["timings_s"])
