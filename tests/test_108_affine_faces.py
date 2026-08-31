"""Tests for item 108 — affine-driven anatomical face mapping.

Covers all 11 Acceptance Criteria plus adversarial/edge-case inputs from the
item spec's Testing Strategy.

The defect (``docs/aide/items/108-affine-driven-face-mapping.md``):
``segfacet.features.geometry.compute_label_geometry`` hardcodes
``x == 0 -> touches_inferior``, ``y == 0 -> touches_left``,
``z == 0 -> touches_anterior`` (and the mirrored high-face flags), regardless
of the volume's affine. Since item 094, every volume loaded through
``segfacet.io`` is reoriented to RAS (array axis 0 = left->right, axis 1 =
posterior->anterior, axis 2 = inferior->superior), so every ``touches_*`` flag
on real (loaded) data is systematically mis-named. The fix derives the
axis->face mapping from the affine instead.

- AC1: no hardcoded axis index remains in the assignment path (source
  introspection of ``compute_label_geometry``).
- AC2: a RAS-resolving affine names each of the six faces correctly.
- AC3: the same anatomical volume, stored in RAS and in a different axis
  order (PIL), yields identical ``touches_*`` flags after loading through
  ``segfacet.io.load_volume``.
- AC4: a hand-built array with the spine along array axis 0, and an affine
  that says so, reports the cranio-caudal faces as superior/inferior.
- AC5: an explicit before/after regression, pre-fix values commented.
- AC6: a ``border`` finding names the correct face.
- AC7: the ``coverage`` rule's FOV-truncation derivation (via
  ``heuristics/fov.py``) respects the corrected superior/inferior flags.
- AC8: on the committed corpus, ``border``/``coverage`` finding presence and
  offending labels are unchanged relative to the committed goldens; only
  face names in the (unchecked) ``reason`` text may differ.
- AC9: missing / singular / oblique affines have a documented, deterministic
  outcome (a clear error, or a stable result across repeated calls).
- AC10: the module docstring states the affine-derived contract and no
  longer claims an any-orientation convention.
- AC11: regenerating the golden corpus twice is byte-identical.

Adversarial / edge-case scenarios included: a single-voxel label touching
several faces; an anisotropic volume; a volume with two axes of equal
extent; a flipped (negative-determinant) affine.

All fixtures are built in-memory or under pytest's ``tmp_path`` — no
absolute filesystem paths, no network.
"""

from __future__ import annotations

import inspect
import pathlib
import re

import nibabel as nib
import numpy as np
import pytest

from segfacet.config import (
    SUPPORTED_SCHEMA_VERSION,
    default_config,
    load_config,
)
from segfacet.features import geometry as geometry_module
from segfacet.features.geometry import compute_label_geometry
from segfacet.heuristics.border import BorderRule
from segfacet.heuristics.coverage import CoverageRule
from segfacet.io import load_volume
from segfacet.pipeline import extract_feature_record

import segfacet.synth  # noqa: F401 -- triggers self-registration of every operator
from segfacet.synth.corpus import load_manifest
from segfacet.synth.golden import build_report_for_case, write_goldens


# =========================================================================== #
# Helpers
# =========================================================================== #

_ALL_FACES = (
    "touches_superior",
    "touches_inferior",
    "touches_left",
    "touches_right",
    "touches_anterior",
    "touches_posterior",
)

# World-axis index (0=L/R, 1=P/A, 2=I/S) and sign for each anatomical axcode
# letter, used only to *build* affines describing a chosen axcode triple --
# not imported from segfacet, so these tests do not assume the production
# mapping mechanism, only its observable result.
_WORLD_AXIS = {
    "L": (0, -1), "R": (0, 1),
    "P": (1, -1), "A": (1, 1),
    "I": (2, -1), "S": (2, 1),
}


def _affine_for_axcodes(spacing, axcodes) -> np.ndarray:
    """Build a 4x4 axis-permutation/flip affine (no rotation) whose
    ``nib.aff2axcodes`` resolves to *axcodes*, with *spacing* magnitudes on
    each array axis. Zero origin -- translation never affects axcodes."""
    m = np.zeros((4, 4))
    m[3, 3] = 1.0
    for arr_axis, code in enumerate(axcodes):
        world_axis, sign = _WORLD_AXIS[code]
        m[world_axis, arr_axis] = sign * float(spacing[arr_axis])
    return m


def _seg_with_block(shape, box, spacing=(1.0, 1.0, 1.0), axcodes=("R", "A", "S")):
    """A label-1 block (half-open voxel ranges) in an all-zero volume, with
    an affine resolving to *axcodes*."""
    (x0, x1), (y0, y1), (z0, z1) = box
    data = np.zeros(shape, dtype=np.uint16)
    data[x0:x1, y0:y1, z0:z1] = 1
    affine = _affine_for_axcodes(spacing, axcodes)
    return nib.Nifti1Image(data, affine)


def _flags_dict(geom) -> dict:
    return {face: getattr(geom, face) for face in _ALL_FACES}


def _reoriented(img: nib.Nifti1Image, axcodes) -> nib.Nifti1Image:
    """Return *img* re-stored under a different axis order describing the
    *same* physical anatomy (via nibabel's own reorientation machinery)."""
    cur = nib.orientations.io_orientation(img.affine)
    targ = nib.orientations.axcodes2ornt(axcodes)
    transform = nib.orientations.ornt_transform(cur, targ)
    return img.as_reoriented(transform)


def _write_yaml(tmp_path: pathlib.Path, content: str, name: str = "config.yaml") -> pathlib.Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def _coverage_yaml_header() -> str:
    return (
        f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
        "rules:\n"
        "  coverage:\n"
        "    params:\n"
    )


def _levels_yaml_list(levels, indent: str = "      ") -> str:
    lines = [f"{indent}expected_levels:\n"]
    for lvl in levels:
        lines.append(f"{indent}  - {lvl}\n")
    return "".join(lines)


def _assert_documented_outcome(seg_img, label=1):
    """AC9: either a clear, non-blank error, or a deterministic result across
    two independent calls -- never a silently inconsistent mis-assignment."""
    try:
        r1 = compute_label_geometry(seg_img, label=label)
    except Exception as exc:
        assert str(exc).strip(), "AC9 error path must carry a non-blank message"
        return
    r2 = compute_label_geometry(seg_img, label=label)
    for face in _ALL_FACES:
        assert getattr(r1, face) == getattr(r2, face), (
            f"AC9 fallback path must be deterministic across calls; "
            f"{face} differed"
        )


# =========================================================================== #
# AC1 — the mapping is derived, not assumed
# =========================================================================== #


_HARDCODED_PATTERNS = (
    r"touches_inferior\s*=\s*bool\(\s*x_min_v\s*==\s*0\s*\)",
    r"touches_superior\s*=\s*bool\(\s*x_max_v\s*==\s*shape\[0\]\s*-\s*1\s*\)",
    r"touches_left\s*=\s*bool\(\s*y_min_v\s*==\s*0\s*\)",
    r"touches_right\s*=\s*bool\(\s*y_max_v\s*==\s*shape\[1\]\s*-\s*1\s*\)",
    r"touches_anterior\s*=\s*bool\(\s*z_min_v\s*==\s*0\s*\)",
    r"touches_posterior\s*=\s*bool\(\s*z_max_v\s*==\s*shape\[2\]\s*-\s*1\s*\)",
)


@pytest.mark.parametrize("pattern", _HARDCODED_PATTERNS)
def test_ac1_no_hardcoded_axis_literal_assignment(pattern):
    """AC1: none of the six pre-fix hardcoded axis==index assignments remain
    in compute_label_geometry's source."""
    src = inspect.getsource(geometry_module.compute_label_geometry)
    assert re.search(pattern, src) is None, (
        f"a hardcoded axis assignment matching {pattern!r} is still present"
    )


def test_ac1_assignment_path_reads_the_affine():
    """AC1: the face-assignment logic actually consults the image's
    ``.affine`` attribute (the derivation source), not merely a docstring
    mention of the word -- shape/index literals alone cannot satisfy this."""
    src = inspect.getsource(geometry_module.compute_label_geometry)
    assert re.search(r"\.affine\b", src) is not None, (
        "compute_label_geometry's body does not appear to read seg_img.affine "
        "anywhere -- the mapping cannot be affine-derived"
    )


# =========================================================================== #
# AC2 — RAS volumes are named correctly
# =========================================================================== #


@pytest.mark.parametrize(
    "box, expected_face",
    [
        (((0, 3), (2, 5), (2, 5)), "touches_left"),
        (((5, 8), (2, 5), (2, 5)), "touches_right"),
        (((2, 5), (0, 3), (2, 5)), "touches_posterior"),
        (((2, 5), (5, 8), (2, 5)), "touches_anterior"),
        (((2, 5), (2, 5), (0, 3)), "touches_inferior"),
        (((2, 5), (2, 5), (5, 8)), "touches_superior"),
    ],
    ids=[
        "low-x-left", "high-x-right",
        "low-y-posterior", "high-y-anterior",
        "low-z-inferior", "high-z-superior",
    ],
)
def test_ac2_ras_face_named_correctly(box, expected_face):
    """AC2: for a RAS-resolving affine, each of the six single-face touches
    is reported under its anatomically-correct flag, and only that flag."""
    seg = _seg_with_block((8, 8, 8), box)  # default axcodes = RAS
    result = compute_label_geometry(seg, label=1)
    flags = _flags_dict(result)
    for face in _ALL_FACES:
        assert flags[face] == (face == expected_face), (
            f"box {box} (RAS affine): expected only {expected_face} True; "
            f"got {flags}"
        )


# =========================================================================== #
# AC3 — orientation invariance
# =========================================================================== #


def test_ac3_orientation_invariance_ras_vs_pil(tmp_path):
    """AC3: the same anatomical volume, stored on disk in RAS and in PIL
    axis order, yields identical touches_* flags after loading through
    segfacet.io.load_volume."""
    shape = (5, 6, 7)
    spacing = (2.0, 1.5, 3.0)
    box = ((0, 2), (2, 4), (5, 7))  # touches low-x and high-z simultaneously

    seg_ras = _seg_with_block(shape, box, spacing=spacing)
    seg_pil = _reoriented(seg_ras, ("P", "I", "L"))

    ras_path = tmp_path / "ras.nii.gz"
    pil_path = tmp_path / "pil.nii.gz"
    nib.save(seg_ras, str(ras_path))
    nib.save(seg_pil, str(pil_path))

    vol_ras = load_volume(ras_path, integer_labels=True)
    vol_pil = load_volume(pil_path, integer_labels=True)

    img_ras = nib.Nifti1Image(vol_ras.data.astype("int32"), vol_ras.affine)
    img_pil = nib.Nifti1Image(vol_pil.data.astype("int32"), vol_pil.affine)

    result_ras = compute_label_geometry(img_ras, label=1)
    result_pil = compute_label_geometry(img_pil, label=1)

    assert _flags_dict(result_ras) == _flags_dict(result_pil)


def test_ac3_pil_array_genuinely_differs_before_loading():
    """Guards against a vacuous AC3 test: the raw PIL-stored array is not
    trivially identical to the RAS-stored one before reorientation."""
    shape = (5, 6, 7)
    box = ((0, 2), (2, 4), (5, 7))
    seg_ras = _seg_with_block(shape, box)
    seg_pil = _reoriented(seg_ras, ("P", "I", "L"))
    data_ras = np.asanyarray(seg_ras.dataobj)
    data_pil = np.asanyarray(seg_pil.dataobj)
    assert data_ras.shape != data_pil.shape or not np.array_equal(data_ras, data_pil)


# =========================================================================== #
# AC4 — hand-built arrays are correct too
# =========================================================================== #


def test_ac4_handbuilt_axis0_spine_reports_cranio_caudal_not_leftright():
    """AC4: a fixture built with the spine along array axis 0, whose affine
    says axis 0 carries the S/I direction, reports the cranio-caudal faces
    as superior/inferior -- never left/right."""
    axcodes = ("S", "R", "A")

    seg_low = _seg_with_block((8, 8, 8), ((0, 3), (2, 5), (2, 5)), axcodes=axcodes)
    result_low = compute_label_geometry(seg_low, label=1)
    assert result_low.touches_inferior is True
    assert result_low.touches_superior is False
    assert result_low.touches_left is False
    assert result_low.touches_right is False
    assert result_low.touches_anterior is False
    assert result_low.touches_posterior is False

    seg_high = _seg_with_block((8, 8, 8), ((5, 8), (2, 5), (2, 5)), axcodes=axcodes)
    result_high = compute_label_geometry(seg_high, label=1)
    assert result_high.touches_superior is True
    assert result_high.touches_inferior is False
    assert result_high.touches_left is False
    assert result_high.touches_right is False


# =========================================================================== #
# AC5 — the pre-fix mapping is pinned as wrong
# =========================================================================== #


def test_ac5_pinned_regression_x_low_face_under_ras_affine():
    """AC5 regression pin. Fixture: a label-1 block occupying x[0:3], y[2:5],
    z[2:5] in an 8x8x8 volume with a RAS-resolving diagonal affine (RAS: axis
    0 = left->right, axis 1 = posterior->anterior, axis 2 = inferior->
    superior).

    Pre-fix (WRONG, geometry.py:251 hardcoded ``x == 0 -> touches_inferior``):
        touches_inferior=True, touches_superior=False, touches_left=False,
        touches_right=False, touches_anterior=False, touches_posterior=False

    Corrected (affine-derived: x==0 is the low end of the L/R axis, i.e.
    "left" for a RAS affine):
        touches_left=True, all five other flags False

    This test is demonstrated to fail against the pre-fix implementation
    (which reports touches_inferior=True, touches_left=False here).
    """
    seg = _seg_with_block((8, 8, 8), ((0, 3), (2, 5), (2, 5)))  # default RAS
    result = compute_label_geometry(seg, label=1)

    assert result.touches_left is True
    assert result.touches_inferior is False
    assert result.touches_superior is False
    assert result.touches_right is False
    assert result.touches_anterior is False
    assert result.touches_posterior is False


# =========================================================================== #
# AC6 — border findings name the right face
# =========================================================================== #


def _three_level_case_with_posterior_crop():
    """Three recognised, non-overlapping vertebra labels (L1=20, L2=21,
    L3=22) stacked along array axis 0; L2 (a mid-spine, non-terminal level)
    additionally touches the low-y face -- "posterior" under the RAS
    affine, "left" under the pre-fix hardcoded convention."""
    shape = (16, 16, 16)
    data = np.zeros(shape, dtype=np.uint16)
    data[1:3, 6:10, 6:10] = 20   # L1
    data[6:8, 0:4, 6:10] = 21    # L2 -- touches y=0
    data[11:13, 6:10, 6:10] = 22  # L3
    affine = _affine_for_axcodes((1.0, 1.0, 1.0), ("R", "A", "S"))
    return nib.Nifti1Image(data, affine)


def test_ac6_border_finding_names_posterior_not_left():
    """AC6: cropping a mid-spine vertebra at the volume's low-y face
    produces a border finding naming it "posterior" (the RAS-correct face),
    not "left" (the pre-fix hardcoded face)."""
    seg_img = _three_level_case_with_posterior_crop()
    config = default_config()
    record = extract_feature_record(seg_img, config)

    findings = BorderRule().evaluate(record, config)
    assert len(findings) == 1, findings
    finding = findings[0]
    assert finding.labels == frozenset({21})
    assert "posterior" in finding.reason, finding.reason
    assert "left" not in finding.reason, finding.reason


# =========================================================================== #
# AC7 — fov findings name the right face (via heuristics/fov.py)
# =========================================================================== #


def _three_level_case_with_superior_touch():
    """Three recognised levels (L1=20, L2=21, L3=22); L1 (the most-superior
    present level) genuinely touches the volume's high-z face -- "superior"
    under the RAS affine. Under the pre-fix hardcoded convention, z==max
    maps to touches_posterior, never touches_superior."""
    shape = (16, 16, 16)
    data = np.zeros(shape, dtype=np.uint16)
    data[1:3, 6:10, 13:16] = 20   # L1 -- touches z=15 (max)
    data[6:8, 6:10, 6:10] = 21    # L2
    data[11:13, 6:10, 6:10] = 22  # L3
    affine = _affine_for_axcodes((1.0, 1.0, 1.0), ("R", "A", "S"))
    return nib.Nifti1Image(data, affine)


def test_ac7_coverage_fov_truncation_respects_superior_face(tmp_path):
    """AC7: L1 genuinely touches the image's superior face, so the
    corrected touches_superior flag must mark the superior end of the
    present-level span as FOV-truncated -- suppressing the incomplete-span
    finding for the beyond-superior expected level T12 (derived via
    heuristics/fov.py's derive_fov_coverage, shared by coverage/border)."""
    seg_img = _three_level_case_with_superior_touch()
    content = _coverage_yaml_header() + _levels_yaml_list(
        ["T12", "L1", "L2", "L3", "L4"]
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    record = extract_feature_record(seg_img, cfg)

    findings = CoverageRule().evaluate(record, cfg)
    span = [f for f in findings if f.reason.startswith("Incomplete coverage (span):")]
    assert not any("T12" in f.reason for f in span), (
        "L1 touches the volume's superior face; the corrected affine-derived "
        "touches_superior flag should mark the superior end as FOV-truncated, "
        f"suppressing the 'T12' incomplete-span finding; got {span!r}"
    )


# =========================================================================== #
# AC8 — rule decisions unchanged on the committed corpus
# =========================================================================== #


_MANIFEST = load_manifest()
_CASES = _MANIFEST["cases"]


def _face_insensitive_findings(findings, rule_ids):
    """(rule_id, severity, sorted labels) tuples for the given rule_ids --
    deliberately excludes `reason`, whose face-naming text is exactly what
    this item is authorised to change."""
    return sorted(
        (f["rule_id"], f["severity"], tuple(sorted(f["labels"])))
        for f in findings
        if f["rule_id"] in rule_ids
    )


@pytest.mark.parametrize("case", _CASES, ids=lambda c: c["case_id"])
def test_ac8_border_and_coverage_presence_and_labels_unchanged(case):
    """AC8 (item 126 replacement): for every committed corpus case, the
    (rule_id, severity, labels) triples of every border/coverage finding
    exactly match the pinned pre-098 verdict+findings shape -- only face
    names inside `reason` may differ. Re-pointed at fresh output; the
    committed golden this used to read was retired, see
    docs/aide/golden-decision-table.md's "## Retirement execution log"."""
    from test_098_stray_components import _PRE_098_GOLDEN_VERDICT_AND_FINDINGS

    case_id = case["case_id"]
    if case_id not in _PRE_098_GOLDEN_VERDICT_AND_FINDINGS:
        pytest.skip(f"no pinned pre-098 shape for {case_id!r}")
    report = build_report_for_case(case)
    expected = _PRE_098_GOLDEN_VERDICT_AND_FINDINGS[case_id]

    fresh = _face_insensitive_findings(report["findings"], {"border", "coverage"})
    pinned = _face_insensitive_findings(expected["findings"], {"border", "coverage"})
    assert fresh == pinned, (
        f"case {case_id!r}: border/coverage finding presence or "
        f"offending labels changed -- fresh={fresh!r} pinned={pinned!r}"
    )


# =========================================================================== #
# AC9 — degenerate affine handled explicitly
# =========================================================================== #


def _small_labelmap():
    data = np.zeros((6, 6, 6), dtype=np.uint16)
    data[0:2, 2:4, 2:4] = 1
    return data


def test_ac9_missing_affine_deterministic_outcome():
    """AC9: a NiBabel image with no affine (``affine=None``) yields a clear
    error or a deterministic result -- never a silent mis-assignment."""
    seg = nib.Nifti1Image(_small_labelmap(), None)
    _assert_documented_outcome(seg)


def test_ac9_singular_affine_deterministic_outcome():
    """AC9: a singular affine (zero row -- rank-deficient rotation part)
    yields a clear error or a deterministic result.

    ``nib.Nifti1Image(data, singular_affine)`` itself raises
    (``HeaderDataError``/``LinAlgError``, via NiBabel's own header-affine
    decomposition) before this ever reaches production code -- constructing
    with the singular affine directly would only exercise NiBabel's
    constructor, never ``compute_label_geometry``'s own degenerate-affine
    handling that AC9 documents. Built instead with a harmless placeholder
    affine, then the singular affine is assigned onto the image post
    construction (``Nifti1Image.affine`` is a settable property that writes
    straight into the header, with no re-validation) so the object actually
    reaches ``compute_label_geometry`` carrying the singular affine (item
    116 AC14)."""
    affine = np.array(
        [[1.0, 0.0, 0.0, 0.0],
         [0.0, 1.0, 0.0, 0.0],
         [0.0, 0.0, 0.0, 0.0],
         [0.0, 0.0, 0.0, 1.0]]
    )
    seg = nib.Nifti1Image(_small_labelmap(), np.eye(4))
    seg.affine[:] = affine
    _assert_documented_outcome(seg)


def test_ac9_oblique_nonaxis_aligned_affine_deterministic_outcome():
    """AC9: a genuinely oblique (45-degree rotated, non-axis-aligned)
    affine yields a clear error or a deterministic result."""
    theta = np.pi / 4.0
    c, s = np.cos(theta), np.sin(theta)
    affine = np.array(
        [[c, -s, 0.0, 0.0],
         [s, c, 0.0, 0.0],
         [0.0, 0.0, 1.0, 0.0],
         [0.0, 0.0, 0.0, 1.0]]
    )
    seg = nib.Nifti1Image(_small_labelmap(), affine)
    _assert_documented_outcome(seg)


# =========================================================================== #
# AC10 — the docstring states the new contract
# =========================================================================== #


def test_ac10_docstring_no_longer_claims_any_orientation_convention():
    """AC10: the module docstring no longer defends the mapping as "a
    pragmatic convention for tools that work in any orientation"."""
    doc = (geometry_module.__doc__ or "").lower()
    assert "any orientation" not in doc, (
        "geometry.py's docstring still claims the stale any-orientation "
        "convention"
    )


def test_ac10_docstring_states_affine_derived_contract():
    """AC10: the module docstring documents the affine as the mapping's
    source."""
    doc = (geometry_module.__doc__ or "").lower()
    assert "affine" in doc, (
        "geometry.py's docstring does not mention the affine as the source "
        "of the touches_* face mapping"
    )


# =========================================================================== #
# AC11 — goldens regenerate consistently
# =========================================================================== #


def test_ac11_regenerating_goldens_twice_is_byte_identical(tmp_path):
    """AC11: write_goldens into two fresh directories produces byte-for-byte
    identical files."""
    dest1 = tmp_path / "regen1"
    dest2 = tmp_path / "regen2"
    write_goldens(dest1)
    write_goldens(dest2)

    files1 = {p.name: p.read_bytes() for p in dest1.glob("*.json")}
    files2 = {p.name: p.read_bytes() for p in dest2.glob("*.json")}
    assert files1 == files2
    assert files1  # sanity: not vacuously empty


# =========================================================================== #
# Adversarial — single-voxel label touching several faces
# =========================================================================== #


def test_adv_single_voxel_corner_touches_exactly_left_posterior_inferior():
    """Adversarial: a single voxel at the (0,0,0) corner of a RAS-affine
    volume touches exactly left, posterior, and inferior -- not the pre-fix
    inferior/left/anterior triple."""
    seg = _seg_with_block((6, 6, 6), ((0, 1), (0, 1), (0, 1)))
    result = compute_label_geometry(seg, label=1)
    flags = _flags_dict(result)
    assert flags["touches_left"] is True
    assert flags["touches_posterior"] is True
    assert flags["touches_inferior"] is True
    assert flags["touches_right"] is False
    assert flags["touches_anterior"] is False
    assert flags["touches_superior"] is False


# =========================================================================== #
# Adversarial — anisotropic volume
# =========================================================================== #


def test_adv_anisotropic_spacing_does_not_affect_face_identity():
    """Adversarial: highly anisotropic voxel spacing does not change which
    face a border-touching label is assigned to -- only the axis order/sign
    of the affine's rotation part matters."""
    seg = _seg_with_block(
        (10, 10, 10), ((0, 2), (4, 6), (4, 6)), spacing=(0.5, 2.0, 4.0)
    )
    result = compute_label_geometry(seg, label=1)
    flags = _flags_dict(result)
    assert flags["touches_left"] is True
    assert sum(flags.values()) == 1


# =========================================================================== #
# Adversarial — two axes of equal extent
# =========================================================================== #


def test_adv_symmetric_shape_two_equal_axes_no_axis_confusion():
    """Adversarial: axis 0 and axis 1 share the same length (8); a label
    touching only the axis-0 face must not be mistakenly attributed to
    axis 1's face."""
    seg = _seg_with_block((8, 8, 10), ((0, 2), (2, 4), (2, 4)))
    result = compute_label_geometry(seg, label=1)
    flags = _flags_dict(result)
    assert flags["touches_left"] is True
    assert sum(flags.values()) == 1


# =========================================================================== #
# Adversarial — flipped (negative-determinant) affine
# =========================================================================== #


def test_adv_flipped_negative_determinant_affine_flips_face_assignment():
    """Adversarial: an affine whose x-axis direction is flipped relative to
    plain RAS (axcodes LAS instead of RAS, negative determinant) flips which
    physical side array-axis-0's low index touches."""
    axcodes = ("L", "A", "S")
    affine = _affine_for_axcodes((1.0, 1.0, 1.0), axcodes)
    assert np.linalg.det(affine[:3, :3]) < 0, "fixture sanity: expected a mirrored affine"

    seg = _seg_with_block((8, 8, 8), ((0, 3), (2, 5), (2, 5)), axcodes=axcodes)
    result = compute_label_geometry(seg, label=1)
    # axis 0's positive direction is now Left, so low index (0) is Right.
    assert result.touches_right is True
    assert result.touches_left is False
    assert result.touches_superior is False
    assert result.touches_inferior is False
    assert result.touches_anterior is False
    assert result.touches_posterior is False
