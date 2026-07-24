"""Lightweight, deterministic CPU/GPU feature-extraction performance benchmark
(item 074).

**Timed unit.** This module times exactly one call:
``segfacet.pipeline.extract_feature_record(seg_img, config)`` -- the whole
Stage-2/3 feature-extraction pass over one seg image, which drives every
ported hot path (``geometry``, ``components``, ``centroids``,
``fragmentation``, ``spline``, ``spline_offset``).

**Backend selection.** A backend is selected for the timed call by setting the
``SEGFACET_BACKEND`` environment variable (item 071) around each timed block and
invoking the **unmodified** ``extract_feature_record``: item 072's ported
feature functions resolve ``backend=None -> segfacet.backend.get_backend()`` at
call time, which honours the env var. No ``pipeline.py`` / ``cli.py`` change is
needed here.

**No absolute-timing intent -- structural correctness only.** This benchmark
makes no claim about GPU-vs-CPU speed and no test compares a timing to a fixed
second-count threshold (contributor/CI hardware varies too much for that to be
meaningful). It only guarantees a well-formed, schema-valid, parseable JSON
report describing the backend(s) actually run.

**Regenerate, do not commit.** The report is produced on demand via
``run_benchmark`` / the ``python -m segfacet.benchmark`` script entry point and
written to a caller-chosen path; timings are non-deterministic and
hardware-specific, so no report is ever committed to the repository.

**CuPy-gated GPU path.** The GPU backend is only ever included in
``tokens``/``backends`` when ``segfacet.backend.cupy_available()`` is ``True``.
This module never imports ``cupy`` at module scope -- it is imported (if at
all) transitively through ``segfacet.backend.get_backend`` only when the GPU
backend is actually resolved, and the device-synchronisation call
(``cupy.cuda.Stream.null.synchronize()``) used to get an accurate GPU timing
is itself only ever reached on that same GPU path.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from pathlib import Path

import segfacet.backend
from segfacet.config import bundled_default_config
from segfacet.pipeline import extract_feature_record
from segfacet.synth.corpus import load_manifest
from segfacet.synth.regression import loaded_seg_image

__all__ = [
    "run_benchmark",
    "write_report",
    "main",
    "BENCHMARK_VERSION",
    "TIMED_UNIT",
]

#: Schema version for the JSON report emitted by :func:`run_benchmark` /
#: :func:`write_report`.
BENCHMARK_VERSION = "1"

#: Name of the callable this module times (see module docstring).
TIMED_UNIT = "extract_feature_record"

#: Default number of timed repeats per backend.
DEFAULT_ITERATIONS = 5

#: Default number of untimed warmup repeats per backend.
DEFAULT_WARMUP = 1


def _load_fixture(case_id):
    """Load the benchmark's default (or explicitly requested) fixture.

    Returns ``(seg_img, config, fixture_meta)`` where ``fixture_meta`` is a
    JSON-native dict identifying the selected committed corpus case.
    """
    manifest = load_manifest()
    cases = manifest["cases"]

    selected_case = None
    selected_seg_img = None

    if case_id is not None:
        for case in cases:
            if case["case_id"] == case_id:
                selected_case = case
                selected_seg_img = loaded_seg_image(case)
                break
        if selected_case is None:
            raise ValueError(
                f"case_id {case_id!r} not found in the committed corpus manifest"
            )
    else:
        for case in cases:
            seg_img = loaded_seg_image(case)
            data = seg_img.get_fdata()
            n_labels = len(set(data[data != 0].tolist()))
            if n_labels >= 2:
                selected_case = case
                selected_seg_img = seg_img
                break
        if selected_case is None:
            raise ValueError(
                "no committed corpus case has >= 2 distinct non-zero labels"
            )

    seg_img = selected_seg_img
    data = seg_img.get_fdata()
    n_labels = len(set(data[data != 0].tolist()))

    config = bundled_default_config()

    fixture_meta = {
        "source": "corpus",
        "case_id": selected_case["case_id"],
        "n_labels": int(n_labels),
        "shape": list(seg_img.shape),
        "spacing_mm": [float(z) for z in seg_img.header.get_zooms()[:3]],
    }

    return seg_img, config, fixture_meta


def _time_backend(token, seg_img, config, *, iterations, warmup):
    """Time ``iterations`` calls of :func:`extract_feature_record` under the
    backend named *token* (``"cpu"`` or ``"gpu"``), after ``warmup`` untimed
    calls. Restores the prior ``SEGFACET_BACKEND`` value on exit."""
    env_var = segfacet.backend.ENV_VAR
    had_prior = env_var in os.environ
    prior_value = os.environ.get(env_var)

    try:
        os.environ[env_var] = token

        for _ in range(warmup):
            extract_feature_record(seg_img, config)

        timings_s = []
        for _ in range(iterations):
            start = time.perf_counter()
            extract_feature_record(seg_img, config)
            if token == "gpu":
                import cupy

                cupy.cuda.Stream.null.synchronize()
            end = time.perf_counter()
            timings_s.append(end - start)
    finally:
        if had_prior:
            os.environ[env_var] = prior_value
        else:
            os.environ.pop(env_var, None)

    return {
        "name": token,
        "is_gpu": token == "gpu",
        "iterations": iterations,
        "warmup": warmup,
        "timings_s": [float(t) for t in timings_s],
        "min_s": float(min(timings_s)),
        "mean_s": float(statistics.fmean(timings_s)),
        "median_s": float(statistics.median(timings_s)),
    }


def run_benchmark(*, case_id=None, iterations=DEFAULT_ITERATIONS, warmup=DEFAULT_WARMUP):
    """Run the feature-extraction benchmark on every available backend.

    Loads the default (or explicitly requested) committed-corpus fixture,
    times ``extract_feature_record`` under the ``cpu`` backend (always) and
    the ``gpu`` backend (only when ``segfacet.backend.cupy_available()`` is
    ``True``), and returns a schema-valid report dict (see module docstring /
    item spec for the full schema).
    """
    seg_img, config, fixture_meta = _load_fixture(case_id)

    tokens = ["cpu"]
    if segfacet.backend.cupy_available():
        tokens.append("gpu")

    backends = [
        _time_backend(token, seg_img, config, iterations=iterations, warmup=warmup)
        for token in tokens
    ]

    return {
        "benchmark_version": BENCHMARK_VERSION,
        "timed_unit": TIMED_UNIT,
        "iterations": iterations,
        "warmup": warmup,
        "cupy_available": segfacet.backend.cupy_available(),
        "fixture": fixture_meta,
        "backends": backends,
    }


def write_report(report, out_path):
    """Serialise *report* to JSON at *out_path*."""
    Path(out_path).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    """``python -m segfacet.benchmark`` script entry point.

    Runs :func:`run_benchmark` and writes the resulting report as JSON to
    ``--out``, printing a one-line human-readable summary.
    """
    parser = argparse.ArgumentParser(
        prog="segfacet.benchmark",
        description=(
            "Benchmark segfacet.pipeline.extract_feature_record's wall-clock "
            "time per available compute backend (CPU always, GPU when CuPy "
            "is importable)."
        ),
    )
    parser.add_argument("--out", required=True, help="Path to write the JSON report to.")
    parser.add_argument(
        "--iterations",
        type=int,
        default=DEFAULT_ITERATIONS,
        help=f"Timed repeats per backend (default: {DEFAULT_ITERATIONS}).",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=DEFAULT_WARMUP,
        help=f"Untimed warmup repeats per backend (default: {DEFAULT_WARMUP}).",
    )
    parser.add_argument(
        "--case",
        type=str,
        default=None,
        help="Explicit committed corpus case_id to benchmark (default: auto-selected).",
    )

    args = parser.parse_args(argv)

    report = run_benchmark(
        case_id=args.case, iterations=args.iterations, warmup=args.warmup
    )
    write_report(report, args.out)

    backend_names = ", ".join(b["name"] for b in report["backends"])
    print(
        f"segfacet.benchmark: wrote report to {args.out} "
        f"(backends: {backend_names}; case: {report['fixture']['case_id']}; "
        f"iterations: {report['iterations']}, warmup: {report['warmup']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
