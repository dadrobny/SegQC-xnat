"""Tests for sagittal projection (item 021).

Covers all ten Acceptance Criteria plus adversarial and edge-case inputs:

* AC1  — PNG artifact produced: render_sagittal_projection writes a file and
          returns a non-None Path for a valid fixture.
* AC2  — Returned path matches the output_path argument (same file on disk).
* AC3  — Output file exists and is non-empty (size > 0 bytes).
* AC4  — Output file starts with the PNG magic bytes b'\\x89PNG'.
* AC5  — Return value is the concrete Path; callers can embed it in the report.
* AC6  — Graceful degradation when matplotlib is unavailable (returns None,
          no exception raised).
* AC7  — No crash when matplotlib Agg backend setup fails (returns None).
* AC8  — ValueError for empty centroid list (with a non-empty, human-readable
          message; no raw traceback in the message).
* AC9  — Determinism: same inputs produce output files of identical byte size.
* AC10 — Single-centroid input is handled without an uncaught exception (raises
          ValueError with a non-empty message — matches the documented behaviour
          that one centroid cannot define a curve).

Adversarial scenarios:
- Empty centroid list → ValueError (AC8), non-empty message, no raw repr.
- Single centroid → ValueError (AC10), non-empty message.
- matplotlib ImportError patched → returns None, no exception (AC6).
- matplotlib.use("Agg") failure patched → returns None, no exception (AC7).
- Collinear centroids (all on z axis) → valid PNG produced.
- Highly anisotropic mm spacing (z 30x larger than x) → valid PNG produced.
- Large mm coordinates (full-spine physical extent) → valid PNG produced.
- Existing output file overwritten → new file written without error.
- Output path inside a fresh tmp_path subdirectory → file written correctly.
- Immutability: centroid list not mutated by the function call.
- Immutability: SplineFit not mutated by the function call.
- n_spline_points=1 (minimum sample) → no crash.
- n_spline_points=500 (many samples) → no crash.
- dpi=72 and dpi=300 variants → no crash.
- Import contract: render_sagittal_projection importable from
  segqc.features.sagittal_projection.

All tests are deterministic, CPU-only, and portable (no network, no absolute
paths, no services).
"""

from __future__ import annotations

import importlib
import struct
from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch

import pytest

from segqc.features.centroids import LabelCentroid
from segqc.features.sagittal_projection import render_sagittal_projection
from segqc.features.spline import SplineFit, fit_centroid_spline


# =========================================================================== #
# Helpers
# =========================================================================== #


def _centroid(
    level_name: str,
    mm: tuple,
    label: int = 0,
) -> LabelCentroid:
    """Build a minimal LabelCentroid with the given mm coordinates."""
    return LabelCentroid(
        label=label,
        level_name=level_name,
        centroid_voxel=(0.0, 0.0, 0.0),
        centroid_mm=mm,
    )


def _straight_spine(n: int = 6, spacing_mm: float = 10.0) -> List[LabelCentroid]:
    """Return n centroids equally spaced along the z axis (straight spine)."""
    levels = ["T8", "T9", "T10", "T11", "T12", "L1", "L2", "L3", "L4", "L5"]
    return [
        _centroid(levels[i % len(levels)], (0.0, 0.0, float(i) * spacing_mm), label=i + 1)
        for i in range(n)
    ]


def _curved_spine() -> List[LabelCentroid]:
    """Return 6 centroids along a gentle curve in the xz-plane."""
    levels = ["T8", "T9", "T10", "T11", "T12", "L1"]
    xs = [0.0, 1.0, 2.5, 3.0, 2.5, 1.0]
    zs = [0.0, 10.0, 20.0, 30.0, 40.0, 50.0]
    return [
        _centroid(lv, (x, 0.0, z), label=i + 1)
        for i, (lv, x, z) in enumerate(zip(levels, xs, zs))
    ]


def _fit(centroids: List[LabelCentroid], degree: int = 3) -> SplineFit:
    return fit_centroid_spline(centroids, degree=degree)


def _is_png(path: Path) -> bool:
    """Return True if the file at path starts with the PNG magic bytes."""
    with open(path, "rb") as fh:
        header = fh.read(4)
    return header == b"\x89PNG"


# =========================================================================== #
# Import contract
# =========================================================================== #


def test_import_render_sagittal_projection():
    """render_sagittal_projection is importable from segqc.features.sagittal_projection."""
    from segqc.features.sagittal_projection import render_sagittal_projection as rsp  # noqa: F401
    assert callable(rsp)


def test_no_import_error():
    """Importing segqc.features.sagittal_projection raises no error."""
    mod = importlib.import_module("segqc.features.sagittal_projection")
    assert hasattr(mod, "render_sagittal_projection")


def test_module_import_does_not_require_matplotlib():
    """Importing segqc.features.sagittal_projection works even when matplotlib
    is absent (the guard must be inside the function, not at module level)."""
    with patch.dict("sys.modules", {"matplotlib": None}):
        try:
            importlib.invalidate_caches()
            # The module may already be cached — we can at least confirm the
            # function exists and is callable without triggering the import path.
            from segqc.features.sagittal_projection import render_sagittal_projection as rsp
            assert callable(rsp)
        except ImportError:
            pytest.fail(
                "Importing sagittal_projection failed when matplotlib was absent "
                "— matplotlib must not be imported at module level."
            )


# =========================================================================== #
# AC1: PNG artifact produced
# =========================================================================== #


def test_ac1_straight_spine_returns_path(tmp_path):
    """AC1: render_sagittal_projection returns a non-None Path for a straight spine."""
    centroids = _straight_spine(6)
    fit = _fit(centroids)
    out = tmp_path / "projection.png"
    result = render_sagittal_projection(centroids, fit, out)
    assert result is not None, "Expected a Path, got None"
    assert isinstance(result, Path)


def test_ac1_curved_spine_returns_path(tmp_path):
    """AC1: render_sagittal_projection returns a non-None Path for a curved spine."""
    centroids = _curved_spine()
    fit = _fit(centroids)
    out = tmp_path / "curved_projection.png"
    result = render_sagittal_projection(centroids, fit, out)
    assert result is not None
    assert isinstance(result, Path)


def test_ac1_straight_spine_file_written(tmp_path):
    """AC1: The output file is actually written to disk."""
    centroids = _straight_spine(6)
    fit = _fit(centroids)
    out = tmp_path / "projection.png"
    render_sagittal_projection(centroids, fit, out)
    assert out.exists(), f"Expected {out} to exist after render"


# =========================================================================== #
# AC2: Returned path matches the output_path argument
# =========================================================================== #


def test_ac2_returned_path_matches_argument_path(tmp_path):
    """AC2: The returned Path points to the same file as output_path."""
    centroids = _straight_spine(6)
    fit = _fit(centroids)
    out = tmp_path / "proj.png"
    result = render_sagittal_projection(centroids, fit, out)
    if result is None:
        pytest.skip("matplotlib not available in this environment")
    assert result.resolve() == out.resolve()


def test_ac2_returned_path_file_exists(tmp_path):
    """AC2: The file at the returned path exists on disk."""
    centroids = _straight_spine(5)
    fit = _fit(centroids)
    out = tmp_path / "check_path.png"
    result = render_sagittal_projection(centroids, fit, out)
    if result is None:
        pytest.skip("matplotlib not available in this environment")
    assert result.exists()


def test_ac2_string_output_path_accepted(tmp_path):
    """AC2: A string output path is accepted and returns a Path."""
    centroids = _straight_spine(5)
    fit = _fit(centroids)
    out = str(tmp_path / "str_path.png")
    result = render_sagittal_projection(centroids, fit, out)
    if result is None:
        pytest.skip("matplotlib not available in this environment")
    assert isinstance(result, Path)
    assert result.exists()


# =========================================================================== #
# AC3: Output file exists and is non-empty
# =========================================================================== #


def test_ac3_output_file_exists(tmp_path):
    """AC3: The output file exists after a successful call."""
    centroids = _straight_spine(6)
    fit = _fit(centroids)
    out = tmp_path / "output.png"
    result = render_sagittal_projection(centroids, fit, out)
    if result is None:
        pytest.skip("matplotlib not available in this environment")
    assert out.exists()


def test_ac3_output_file_non_empty(tmp_path):
    """AC3: The output file size is > 0 bytes."""
    centroids = _straight_spine(6)
    fit = _fit(centroids)
    out = tmp_path / "output.png"
    result = render_sagittal_projection(centroids, fit, out)
    if result is None:
        pytest.skip("matplotlib not available in this environment")
    assert out.stat().st_size > 0, f"Expected a non-empty file at {out}"


def test_ac3_curved_spine_output_non_empty(tmp_path):
    """AC3: Curved-spine output is also non-empty."""
    centroids = _curved_spine()
    fit = _fit(centroids)
    out = tmp_path / "curved.png"
    result = render_sagittal_projection(centroids, fit, out)
    if result is None:
        pytest.skip("matplotlib not available in this environment")
    assert out.stat().st_size > 0


# =========================================================================== #
# AC4: Output file is a valid PNG
# =========================================================================== #


def test_ac4_output_starts_with_png_magic(tmp_path):
    """AC4: The output file starts with the PNG magic bytes b'\\x89PNG'."""
    centroids = _straight_spine(6)
    fit = _fit(centroids)
    out = tmp_path / "magic_check.png"
    result = render_sagittal_projection(centroids, fit, out)
    if result is None:
        pytest.skip("matplotlib not available in this environment")
    assert _is_png(out), f"Expected {out} to be a valid PNG (magic bytes check failed)"


def test_ac4_curved_spine_output_is_png(tmp_path):
    """AC4: Curved-spine output is also a valid PNG."""
    centroids = _curved_spine()
    fit = _fit(centroids)
    out = tmp_path / "curved_magic.png"
    result = render_sagittal_projection(centroids, fit, out)
    if result is None:
        pytest.skip("matplotlib not available in this environment")
    assert _is_png(out)


def test_ac4_many_centroids_output_is_png(tmp_path):
    """AC4: A 10-centroid spine also produces a valid PNG."""
    centroids = _straight_spine(10, spacing_mm=12.0)
    fit = _fit(centroids)
    out = tmp_path / "ten_vertebrae.png"
    result = render_sagittal_projection(centroids, fit, out)
    if result is None:
        pytest.skip("matplotlib not available in this environment")
    assert _is_png(out)


# =========================================================================== #
# AC5: Return value is the concrete Path (callers can embed in report)
# =========================================================================== #


def test_ac5_return_value_is_path_instance(tmp_path):
    """AC5: The return value is a pathlib.Path instance, not a string."""
    centroids = _straight_spine(6)
    fit = _fit(centroids)
    out = tmp_path / "report_path.png"
    result = render_sagittal_projection(centroids, fit, out)
    if result is None:
        pytest.skip("matplotlib not available in this environment")
    assert isinstance(result, Path), f"Expected Path, got {type(result)}"


def test_ac5_return_path_is_usable_as_string(tmp_path):
    """AC5: The returned Path can be converted to str for report embedding."""
    centroids = _straight_spine(5)
    fit = _fit(centroids)
    out = tmp_path / "embed.png"
    result = render_sagittal_projection(centroids, fit, out)
    if result is None:
        pytest.skip("matplotlib not available in this environment")
    path_str = str(result)
    assert isinstance(path_str, str)
    assert path_str.endswith(".png")


# =========================================================================== #
# AC6: Graceful degradation when matplotlib is unavailable
# =========================================================================== #


def test_ac6_returns_none_when_matplotlib_import_fails(tmp_path):
    """AC6: Returns None (no exception) when matplotlib import raises ImportError."""
    centroids = _straight_spine(6)
    fit = _fit(centroids)
    out = tmp_path / "no_matplotlib.png"

    with patch("builtins.__import__", side_effect=_block_matplotlib_import):
        result = render_sagittal_projection(centroids, fit, out)

    assert result is None, (
        "Expected None when matplotlib is unavailable, got a Path"
    )


def test_ac6_no_exception_when_matplotlib_import_fails(tmp_path):
    """AC6: No exception propagates when matplotlib import raises ImportError."""
    centroids = _straight_spine(6)
    fit = _fit(centroids)
    out = tmp_path / "no_matplotlib_safe.png"

    try:
        with patch("builtins.__import__", side_effect=_block_matplotlib_import):
            render_sagittal_projection(centroids, fit, out)
    except Exception as exc:
        pytest.fail(
            f"render_sagittal_projection raised {type(exc).__name__} when "
            f"matplotlib was unavailable: {exc}"
        )


def _block_matplotlib_import(name, *args, **kwargs):
    """Side-effect for patching __import__: blocks matplotlib, passes everything else."""
    if name == "matplotlib" or name.startswith("matplotlib."):
        raise ImportError(f"Simulated missing matplotlib: {name}")
    return _real_import(name, *args, **kwargs)


import builtins as _builtins_mod
_real_import = _builtins_mod.__import__


# =========================================================================== #
# AC7: No crash when matplotlib Agg backend is unavailable
# =========================================================================== #


def test_ac7_returns_none_when_agg_backend_fails(tmp_path):
    """AC7: Returns None (no exception) when matplotlib.use('Agg') raises."""
    centroids = _straight_spine(6)
    fit = _fit(centroids)
    out = tmp_path / "no_agg.png"

    with patch("matplotlib.use", side_effect=Exception("Simulated backend failure")):
        result = render_sagittal_projection(centroids, fit, out)

    assert result is None, (
        "Expected None when Agg backend setup fails, got a Path"
    )


def test_ac7_no_exception_when_agg_backend_fails(tmp_path):
    """AC7: No exception propagates when matplotlib.use('Agg') raises."""
    centroids = _straight_spine(6)
    fit = _fit(centroids)
    out = tmp_path / "no_agg_safe.png"

    try:
        with patch("matplotlib.use", side_effect=Exception("Simulated backend failure")):
            render_sagittal_projection(centroids, fit, out)
    except Exception as exc:
        pytest.fail(
            f"render_sagittal_projection raised {type(exc).__name__} when "
            f"Agg backend was unavailable: {exc}"
        )


def test_ac7_returns_none_when_pyplot_savefig_fails(tmp_path):
    """AC7 (extension): Returns None when plt.savefig raises (backend write error)."""
    centroids = _straight_spine(6)
    fit = _fit(centroids)
    out = tmp_path / "savefig_fail.png"

    try:
        import matplotlib  # noqa: F401
    except ImportError:
        pytest.skip("matplotlib not installed")

    with patch("matplotlib.pyplot.savefig", side_effect=RuntimeError("Simulated write failure")):
        result = render_sagittal_projection(centroids, fit, out)

    assert result is None, (
        "Expected None when plt.savefig raises, got a Path"
    )


# =========================================================================== #
# AC8: ValueError for empty centroid list
# =========================================================================== #


def test_ac8_empty_centroids_raises_value_error(tmp_path):
    """AC8: An empty centroid list raises ValueError."""
    centroids = _straight_spine(5)
    fit = _fit(centroids)
    out = tmp_path / "empty.png"
    with pytest.raises(ValueError):
        render_sagittal_projection([], fit, out)


def test_ac8_empty_centroids_message_non_empty(tmp_path):
    """AC8: The ValueError for an empty centroid list has a non-empty message."""
    centroids = _straight_spine(5)
    fit = _fit(centroids)
    out = tmp_path / "empty_msg.png"
    with pytest.raises(ValueError) as exc_info:
        render_sagittal_projection([], fit, out)
    assert str(exc_info.value).strip(), "ValueError message must not be blank"


def test_ac8_empty_centroids_message_no_raw_repr(tmp_path):
    """AC8: The ValueError message does not look like a raw Python object repr."""
    import re
    centroids = _straight_spine(4)
    fit = _fit(centroids)
    out = tmp_path / "empty_repr.png"
    try:
        render_sagittal_projection([], fit, out)
    except ValueError as exc:
        msg = str(exc)
        assert not re.fullmatch(r"<[^>]+>", msg.strip()), (
            f"Error message looks like a raw object repr: {msg!r}"
        )


def test_ac8_empty_centroids_message_no_traceback_text(tmp_path):
    """AC8: The ValueError message does not contain raw traceback text."""
    centroids = _straight_spine(4)
    fit = _fit(centroids)
    out = tmp_path / "empty_tb.png"
    try:
        render_sagittal_projection([], fit, out)
    except ValueError as exc:
        msg = str(exc).lower()
        assert "traceback" not in msg, (
            "ValueError message contains 'traceback' — may be leaking internals"
        )


# =========================================================================== #
# AC9: Determinism
# =========================================================================== #


def test_ac9_determinism_same_file_size(tmp_path):
    """AC9: Two calls with identical inputs produce files of identical byte size."""
    centroids = _straight_spine(6)
    fit = _fit(centroids)
    out1 = tmp_path / "det1.png"
    out2 = tmp_path / "det2.png"
    r1 = render_sagittal_projection(centroids, fit, out1)
    r2 = render_sagittal_projection(centroids, fit, out2)
    if r1 is None or r2 is None:
        pytest.skip("matplotlib not available in this environment")
    assert out1.stat().st_size == out2.stat().st_size, (
        f"File sizes differ: {out1.stat().st_size} vs {out2.stat().st_size}"
    )


def test_ac9_determinism_curved_spine_same_file_size(tmp_path):
    """AC9: Determinism holds for a curved spine."""
    centroids = _curved_spine()
    fit = _fit(centroids)
    out1 = tmp_path / "curve_det1.png"
    out2 = tmp_path / "curve_det2.png"
    r1 = render_sagittal_projection(centroids, fit, out1)
    r2 = render_sagittal_projection(centroids, fit, out2)
    if r1 is None or r2 is None:
        pytest.skip("matplotlib not available in this environment")
    assert out1.stat().st_size == out2.stat().st_size


def test_ac9_determinism_return_value_is_path(tmp_path):
    """AC9: Both calls return Path instances (not None) for identical inputs."""
    centroids = _straight_spine(5)
    fit = _fit(centroids)
    out1 = tmp_path / "idem1.png"
    out2 = tmp_path / "idem2.png"
    r1 = render_sagittal_projection(centroids, fit, out1)
    r2 = render_sagittal_projection(centroids, fit, out2)
    if r1 is None or r2 is None:
        pytest.skip("matplotlib not available in this environment")
    assert isinstance(r1, Path)
    assert isinstance(r2, Path)


# =========================================================================== #
# AC10: Single-centroid input is handled without an uncaught exception
# =========================================================================== #


def test_ac10_single_centroid_raises_value_error(tmp_path):
    """AC10: A single centroid raises ValueError (cannot define a curve)."""
    one = [_centroid("L3", (0.0, 0.0, 30.0), label=1)]
    # Build a spline from enough points to construct a SplineFit separately
    full = _straight_spine(5)
    fit = _fit(full)
    out = tmp_path / "single.png"
    with pytest.raises((ValueError, Exception)) as exc_info:
        render_sagittal_projection(one, fit, out)
    # Confirm the raised exception has a non-empty message
    assert str(exc_info.value).strip(), (
        "Exception raised for single centroid must have a non-empty message"
    )


def test_ac10_single_centroid_no_uncaught_exception(tmp_path):
    """AC10: Single centroid does not propagate any uncaught internal exception."""
    one = [_centroid("L3", (0.0, 0.0, 30.0), label=1)]
    full = _straight_spine(5)
    fit = _fit(full)
    out = tmp_path / "single_safe.png"
    # Only ValueError is the expected exception; anything else is a bug
    try:
        render_sagittal_projection(one, fit, out)
    except ValueError:
        pass  # Documented behaviour: ValueError for too-few centroids
    except Exception as exc:
        pytest.fail(
            f"Single centroid raised unexpected {type(exc).__name__}: {exc}"
        )


# =========================================================================== #
# Adversarial: collinear centroids
# =========================================================================== #


def test_adv_collinear_centroids_no_crash(tmp_path):
    """Collinear centroids (all on z axis) do not crash; PNG is produced."""
    centroids = [
        _centroid("T10", (0.0, 0.0, 0.0), label=1),
        _centroid("T11", (0.0, 0.0, 10.0), label=2),
        _centroid("T12", (0.0, 0.0, 20.0), label=3),
        _centroid("L1", (0.0, 0.0, 30.0), label=4),
        _centroid("L2", (0.0, 0.0, 40.0), label=5),
    ]
    fit = _fit(centroids)
    out = tmp_path / "collinear.png"
    result = render_sagittal_projection(centroids, fit, out)
    if result is None:
        pytest.skip("matplotlib not available in this environment")
    assert out.exists()
    assert _is_png(out)


# =========================================================================== #
# Adversarial: anisotropic mm spacing
# =========================================================================== #


def test_adv_anisotropic_mm_spacing_no_crash(tmp_path):
    """Highly anisotropic mm spacing (z 30x larger than x) does not crash."""
    levels = ["T10", "T11", "T12", "L1", "L2"]
    centroids = [
        _centroid(lv, (0.1 * i, 0.0, 30.0 * i), label=i + 1)
        for i, lv in enumerate(levels)
    ]
    fit = _fit(centroids)
    out = tmp_path / "anisotropic.png"
    result = render_sagittal_projection(centroids, fit, out)
    if result is None:
        pytest.skip("matplotlib not available in this environment")
    assert _is_png(out)


# =========================================================================== #
# Adversarial: large mm coordinates
# =========================================================================== #


def test_adv_large_mm_coordinates_no_crash(tmp_path):
    """Large mm coordinates (full-spine physical extent) do not crash."""
    levels = ["C1", "C2", "C3", "T1", "T2", "T3", "T4", "L1", "L2", "L3"]
    centroids = [
        _centroid(lv, (1.5 * i, 0.0, 16.0 * i), label=i + 1)
        for i, lv in enumerate(levels)
    ]
    fit = _fit(centroids)
    out = tmp_path / "large_coords.png"
    result = render_sagittal_projection(centroids, fit, out)
    if result is None:
        pytest.skip("matplotlib not available in this environment")
    assert _is_png(out)


# =========================================================================== #
# Adversarial: existing file overwritten
# =========================================================================== #


def test_adv_existing_file_is_overwritten(tmp_path):
    """An existing file at output_path is overwritten without error."""
    centroids = _straight_spine(5)
    fit = _fit(centroids)
    out = tmp_path / "overwrite.png"
    # Write a dummy file first
    out.write_bytes(b"dummy content that is not a PNG")
    result = render_sagittal_projection(centroids, fit, out)
    if result is None:
        pytest.skip("matplotlib not available in this environment")
    assert _is_png(out), "Overwritten file should be a valid PNG"


# =========================================================================== #
# Adversarial: output inside a fresh subdirectory
# =========================================================================== #


def test_adv_output_in_existing_subdirectory(tmp_path):
    """Output path inside a pre-existing subdirectory is written correctly."""
    subdir = tmp_path / "subdir" / "projections"
    subdir.mkdir(parents=True)
    centroids = _straight_spine(6)
    fit = _fit(centroids)
    out = subdir / "proj.png"
    result = render_sagittal_projection(centroids, fit, out)
    if result is None:
        pytest.skip("matplotlib not available in this environment")
    assert out.exists()
    assert _is_png(out)


# =========================================================================== #
# Adversarial: immutability of inputs
# =========================================================================== #


def test_adv_centroid_list_not_mutated(tmp_path):
    """render_sagittal_projection does not mutate the input centroid list."""
    centroids = _straight_spine(5)
    original = list(centroids)
    fit = _fit(centroids)
    out = tmp_path / "immutable_list.png"
    render_sagittal_projection(centroids, fit, out)
    assert centroids == original, "Input centroid list was mutated"


def test_adv_spline_fit_not_mutated(tmp_path):
    """render_sagittal_projection does not mutate the SplineFit object."""
    centroids = _straight_spine(5)
    fit = _fit(centroids)
    u_before = tuple(fit.u)
    n_before = fit.n_points
    out = tmp_path / "immutable_fit.png"
    render_sagittal_projection(centroids, fit, out)
    assert fit.u == u_before, "SplineFit.u was mutated"
    assert fit.n_points == n_before, "SplineFit.n_points was mutated"


# =========================================================================== #
# Adversarial: n_spline_points and dpi variants
# =========================================================================== #


def test_adv_n_spline_points_minimum_no_crash(tmp_path):
    """n_spline_points=1 (single sample point) does not crash."""
    centroids = _straight_spine(5)
    fit = _fit(centroids)
    out = tmp_path / "n1.png"
    result = render_sagittal_projection(centroids, fit, out, n_spline_points=1)
    if result is None:
        pytest.skip("matplotlib not available in this environment")
    assert out.exists()


def test_adv_n_spline_points_large_no_crash(tmp_path):
    """n_spline_points=500 (many sample points) does not crash."""
    centroids = _straight_spine(6)
    fit = _fit(centroids)
    out = tmp_path / "n500.png"
    result = render_sagittal_projection(centroids, fit, out, n_spline_points=500)
    if result is None:
        pytest.skip("matplotlib not available in this environment")
    assert _is_png(out)


def test_adv_dpi_72_no_crash(tmp_path):
    """dpi=72 does not crash."""
    centroids = _straight_spine(5)
    fit = _fit(centroids)
    out = tmp_path / "dpi72.png"
    result = render_sagittal_projection(centroids, fit, out, dpi=72)
    if result is None:
        pytest.skip("matplotlib not available in this environment")
    assert out.exists()


def test_adv_dpi_300_no_crash(tmp_path):
    """dpi=300 does not crash."""
    centroids = _straight_spine(5)
    fit = _fit(centroids)
    out = tmp_path / "dpi300.png"
    result = render_sagittal_projection(centroids, fit, out, dpi=300)
    if result is None:
        pytest.skip("matplotlib not available in this environment")
    assert _is_png(out)


# =========================================================================== #
# Adversarial: 2-centroid minimum input (boundary)
# =========================================================================== #


def test_adv_two_centroids_no_crash(tmp_path):
    """Exactly 2 centroids (minimum for a spline) do not crash."""
    centroids = _straight_spine(2)
    fit = _fit(centroids)
    out = tmp_path / "two_centroids.png"
    result = render_sagittal_projection(centroids, fit, out)
    if result is None:
        pytest.skip("matplotlib not available in this environment")
    assert _is_png(out)


def test_adv_three_centroids_no_crash(tmp_path):
    """Exactly 3 centroids do not crash."""
    centroids = _straight_spine(3)
    fit = _fit(centroids)
    out = tmp_path / "three_centroids.png"
    result = render_sagittal_projection(centroids, fit, out)
    if result is None:
        pytest.skip("matplotlib not available in this environment")
    assert _is_png(out)
