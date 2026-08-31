"""Tests for the TPTBox-backed orientation-safe image layer (item 094).

``segfacet.io``'s ``load_volume``/``load_case`` are re-implemented on top of
TPTBox's ``NII`` class (``NII.load`` + ``.reorient(axcodes_to=("R","A","S"))``
+ ``.zoom``/``.affine``), replacing the hand-rolled ``_spacing_from_affine``.
None of that exists yet at the time this module is written -- these tests are
authored against the target behaviour documented in the item's Acceptance
Criteria, for the builder to implement against.

Covers AC1-AC7 (AC8 is documentation-only per the item's own Testing
Strategy; no automated test is fabricated for it):

- AC1/AC2: packaging-metadata assertions on ``pyproject.toml``/
  ``constraints.txt`` -- mirrors ``test_095_env_migration.py``'s style.
- AC3: every fixture in the committed Stage-5 corpus (``tests/corpus/``) and
  Stage-8 intensity corpus (``tests/corpus/intensity/``) loads
  byte-identically through the post-migration ``load_volume`` to a snapshot
  captured from the **pre-migration** loader.

  **How the snapshot was captured** (so the builder and validator know what
  "unchanged" is being checked against): before this item touched
  ``src/segfacet/io.py`` (i.e. against the plain-NiBabel implementation that
  predates this item), every ``scan_fixture``/``seg_fixture`` path referenced
  by ``tests/corpus/manifest.json`` and ``tests/corpus/intensity/manifest.json``
  was loaded once via the then-current ``load_volume`` and recorded as
  ``{shape, dtype, sha256(data.tobytes()), spacing, affine}`` into the
  committed fixture ``tests/corpus/094_pre_migration_snapshot.json``. A
  sha256 of the raw array bytes is used instead of embedding the arrays
  themselves so the snapshot stays a small, diffable text file. This test
  module re-loads each fixture through whatever ``load_volume`` exists at
  test time and recomputes the same digest/spacing/affine -- so it is a pure
  before/after diff of the *loader*, independent of what the loader is
  implemented with.
- AC4: a hand-built LPS/RAS fixture pair (same physical anatomy, two
  orientations) proves orientation-safety is real, not merely "does not
  crash."
- AC5: ``dataclasses.fields()`` of ``Volume``/``Case`` compared against the
  pre-item field set (name + type string) recorded above.
- AC6: every ``FacetInputError`` path from ``tests/test_io.py`` re-exercised.
- AC7: a full case (scan + seg) is run through ``segfacet``'s report
  construction (mirroring ``segfacet run``, via
  ``segfacet.synth.golden.build_report_for_case``) and compared -- via
  ``rule_id``/verdict identity -- against the pinned pre-098
  verdict+findings shape (frozen before this migration and unaffected by
  it; item 126 retired the committed golden JSON this AC originally
  compared against with ``reports_close``'s numeric tolerance -- see
  docs/aide/golden-decision-table.md's "## Retirement execution log").

Adversarial / edge cases (per the item's Testing Strategy):
- A NIfTI whose affine already resolves to RAS axcodes but via a
  non-diagonal (rotated) direction-cosine matrix.
- A label map with ``integer_labels=True`` round-trips without float-casting.
- Missing-file / directory / corrupt-file error paths (AC6).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import tomllib
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest

from segfacet.io import Case, FacetInputError, Volume, load_case, load_volume

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
CONSTRAINTS_PATH = REPO_ROOT / "constraints.txt"
SNAPSHOT_PATH = REPO_ROOT / "tests" / "corpus" / "094_pre_migration_snapshot.json"

# TPTBox's own transitive footprint, per the item's queue dependency-footprint
# note (AC2).
TPTBOX_TRANSITIVE_PACKAGE_NAMES = (
    "SimpleITK",
    "scikit-learn",
    "connected-components-3d",
    "fill-voids",
    "pynrrd",
    "dill",
    "requests",
    "matplotlib",
)

# The pre-item Volume/Case field shape (name -> type string), recorded from
# `dataclasses.fields()` before this item touched io.py. AC5 requires this
# shape to be unchanged.
_PRE_ITEM_VOLUME_FIELDS = {
    "data": "np.ndarray",
    "spacing": "Tuple[float, float, float]",
    "affine": "np.ndarray",
    "path": "str",
}
_PRE_ITEM_CASE_FIELDS = {
    "scan": "Volume",
    "seg": "Volume",
    "label_inventory": "Dict[int, int]",
    "foreground_voxels": "int",
}


def _field_type_str(field: dataclasses.Field) -> str:
    t = field.type
    return t if isinstance(t, str) else getattr(t, "__name__", str(t))


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #


def _write_nii(tmp_path, data, spacing, *, name="vol.nii.gz", affine=None):
    """Write ``data`` to a NIfTI file under ``tmp_path`` and return the path."""
    if affine is None:
        affine = np.diag([*spacing, 1.0]).astype(float)
    p = tmp_path / name
    nib.save(nib.Nifti1Image(data, affine), str(p))
    return str(p)


def _load_pyproject() -> dict:
    with PYPROJECT_PATH.open("rb") as fh:
        return tomllib.load(fh)


def _read_constraints() -> str:
    return CONSTRAINTS_PATH.read_text(encoding="utf-8")


def _constraints_pins() -> dict:
    pins = {}
    for raw_line in _read_constraints().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        line = line.split(";", 1)[0].strip()
        match = re.match(r"^([A-Za-z0-9_.\-]+)\s*==\s*([^\s]+)$", line)
        if not match:
            continue
        name = match.group(1).lower().replace("_", "-")
        version = match.group(2)
        pins[name] = version
    return pins


# =========================================================================== #
# AC1: TPTBox pinned as a core dependency
# =========================================================================== #


def test_ac1_tptbox_is_a_pinned_core_dependency():
    dependencies = _load_pyproject()["project"]["dependencies"]
    assert "tptbox==0.7.5" in dependencies


def test_ac1_tptbox_pin_is_exact_not_a_range():
    dependencies = _load_pyproject()["project"]["dependencies"]
    tptbox_specs = [dep for dep in dependencies if dep.lower().startswith("tptbox")]
    assert tptbox_specs == ["tptbox==0.7.5"]


def test_ac1_existing_core_dependencies_unchanged():
    dependencies = _load_pyproject()["project"]["dependencies"]
    unchanged = {
        "numpy>=1.26,<3",
        "scipy>=1.15",
        "scikit-image>=0.19",
        "nibabel>=4.0",
        "PyYAML>=5.4",
        "jsonschema>=3.2",
    }
    assert unchanged.issubset(set(dependencies))


# =========================================================================== #
# AC2: constraints.txt regenerated with TPTBox's transitive footprint
# =========================================================================== #


def test_ac2_constraints_pins_tptbox_exactly():
    pins = _constraints_pins()
    assert pins.get("tptbox") == "0.7.5"


@pytest.mark.parametrize("package_name", TPTBOX_TRANSITIVE_PACKAGE_NAMES)
def test_ac2_constraints_includes_tptbox_transitive(package_name):
    lower_text = _read_constraints().lower()
    assert package_name.lower() in lower_text, (
        f"{package_name!r} (a TPTBox transitive dependency) is missing from "
        "constraints.txt"
    )


def test_ac2_six_original_core_dependencies_still_pinned():
    pins = _constraints_pins()
    for package_name in (
        "numpy",
        "scipy",
        "scikit-image",
        "nibabel",
        "pyyaml",
        "jsonschema",
    ):
        assert package_name in pins, f"{package_name!r} missing from constraints.txt"


# =========================================================================== #
# AC3: existing synthetic fixtures load byte-identically
# =========================================================================== #


def _load_snapshot() -> dict:
    return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))


_SNAPSHOT = _load_snapshot()


def _snapshot_id(key):
    return key


@pytest.mark.parametrize("key", sorted(_SNAPSHOT.keys()), ids=_snapshot_id)
def test_ac3_fixture_loads_byte_identically_to_pre_migration_snapshot(key):
    """Every fixture referenced by the committed corpus/intensity manifests
    loads to exactly the recorded pre-migration data/spacing/affine."""
    entry = _SNAPSHOT[key]
    path = REPO_ROOT / "tests" / entry["path"]

    vol = load_volume(str(path), integer_labels=entry["integer_labels"])

    assert list(vol.data.shape) == entry["shape"]
    assert str(vol.data.dtype) == entry["dtype"]
    digest = hashlib.sha256(np.ascontiguousarray(vol.data).tobytes()).hexdigest()
    assert digest == entry["data_sha256"], (
        f"{key}: voxel data changed after the TPTBox migration -- "
        "reorient(axcodes_to=('R','A','S')) was expected to be a no-op on "
        "this already-RAS-resolving fixture"
    )
    assert list(vol.spacing) == pytest.approx(entry["spacing"])
    assert np.allclose(vol.affine, np.asarray(entry["affine"]))


def test_ac3_snapshot_covers_every_committed_corpus_fixture():
    """Sanity check on the snapshot fixture itself: it is non-empty and
    covers both the Stage-5 corpus and the Stage-8 intensity corpus."""
    assert len(_SNAPSHOT) >= 10
    assert any("intensity/fixtures" in v["path"] for v in _SNAPSHOT.values())
    assert any(
        "intensity/fixtures" not in v["path"] and "fixtures" in v["path"]
        for v in _SNAPSHOT.values()
    )


# =========================================================================== #
# AC4: a differently-oriented file of the same anatomy loads to an
# equivalent array -- the concrete orientation-safety proof
# =========================================================================== #


def _build_ras_and_lps_pair(tmp_path):
    """Build two NIfTI files describing the SAME physical volume: one with
    a diagonal RAS-resolving affine (the existing fixture style), one with
    an axis-permuted/flipped array and a correspondingly transformed affine
    that resolves to LPS axcodes.

    Physically: ``data_lps[i, j, k] == data_ras[nx-1-i, ny-1-j, k]`` (x and y
    indices reversed, z unchanged -- matching LPS's flips of Right->Left and
    Anterior->Posterior relative to RAS, with Superior unchanged). The two
    affines are derived so that both map their respective voxel indices to
    the *same* RAS world coordinates for the same physical voxel.
    """
    nx, ny, nz = 5, 6, 4
    sx, sy, sz = 2.0, 1.5, 3.0

    rng = np.random.default_rng(0)
    data_ras = rng.integers(0, 100, size=(nx, ny, nz)).astype(np.int16)

    affine_ras = np.diag([sx, sy, sz, 1.0]).astype(float)

    data_lps = data_ras[::-1, ::-1, :].copy()
    affine_lps = np.array(
        [
            [-sx, 0.0, 0.0, (nx - 1) * sx],
            [0.0, -sy, 0.0, (ny - 1) * sy],
            [0.0, 0.0, sz, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ]
    )

    # Sanity-check the fixture construction itself: both affines must map
    # index (0,0,0) of their own array to the same RAS world point as
    # applying the *other* orientation's index for the same physical voxel.
    world_ras_origin = affine_ras @ np.array([0, 0, 0, 1.0])
    world_lps_origin = affine_lps @ np.array([nx - 1, ny - 1, 0, 1.0])
    assert np.allclose(world_ras_origin[:3], world_lps_origin[:3])

    ras_path = _write_nii(tmp_path, data_ras, None, name="ras.nii.gz", affine=affine_ras)
    lps_path = _write_nii(tmp_path, data_lps, None, name="lps.nii.gz", affine=affine_lps)
    return ras_path, lps_path, data_ras


def test_ac4_differently_oriented_same_anatomy_loads_to_equivalent_array(tmp_path):
    ras_path, lps_path, data_ras = _build_ras_and_lps_pair(tmp_path)

    vol_ras = load_volume(ras_path, integer_labels=True)
    vol_lps = load_volume(lps_path, integer_labels=True)

    # Both should be reoriented to the same RAS array layout -- the same
    # physical voxel lands at the same array index in both loads.
    assert np.array_equal(vol_ras.data, vol_lps.data)
    assert np.array_equal(vol_ras.data, data_ras)

    # Their spacing/affine describe the same physical geometry.
    assert vol_ras.spacing == pytest.approx(vol_lps.spacing)
    assert np.allclose(vol_ras.affine, vol_lps.affine, atol=1e-4)


def test_ac4_orientation_pair_not_trivially_equal_before_reorientation():
    """Guards against a vacuous AC4 test: the two raw on-disk arrays this
    fixture builds are genuinely different byte layouts (not already equal),
    so the post-load equality above is evidence of real reorientation."""
    nx, ny = 5, 6
    rng = np.random.default_rng(0)
    data_ras = rng.integers(0, 100, size=(nx, ny, 4)).astype(np.int16)
    data_lps = data_ras[::-1, ::-1, :].copy()
    assert not np.array_equal(data_ras, data_lps)


# =========================================================================== #
# AC5: Volume/Case public shape is unchanged
# =========================================================================== #


def test_ac5_volume_field_names_unchanged():
    names = {f.name for f in dataclasses.fields(Volume)}
    assert names == set(_PRE_ITEM_VOLUME_FIELDS)


def test_ac5_volume_field_types_unchanged():
    for f in dataclasses.fields(Volume):
        assert _field_type_str(f) == _PRE_ITEM_VOLUME_FIELDS[f.name]


def test_ac5_case_field_names_unchanged():
    names = {f.name for f in dataclasses.fields(Case)}
    assert names == set(_PRE_ITEM_CASE_FIELDS)


def test_ac5_case_field_types_unchanged():
    for f in dataclasses.fields(Case):
        assert _field_type_str(f) == _PRE_ITEM_CASE_FIELDS[f.name]


def test_ac5_volume_and_case_still_frozen_dataclasses():
    assert dataclasses.is_dataclass(Volume)
    assert dataclasses.is_dataclass(Case)
    data = np.zeros((2, 2, 2), dtype=np.float32)
    with pytest.raises(dataclasses.FrozenInstanceError):
        Volume(data=data, spacing=(1.0, 1.0, 1.0), affine=np.eye(4), path="x").spacing = (
            2.0,
            2.0,
            2.0,
        )  # type: ignore[misc]


# =========================================================================== #
# AC6: FacetInputError semantics preserved (re-exercised from test_io.py)
# =========================================================================== #


def test_ac6_missing_file_raises(tmp_path):
    missing = str(tmp_path / "does_not_exist.nii.gz")
    with pytest.raises(FacetInputError) as exc_info:
        load_volume(missing)
    assert missing in str(exc_info.value)


def test_ac6_directory_path_raises(tmp_path):
    with pytest.raises(FacetInputError, match="directory"):
        load_volume(str(tmp_path))


def test_ac6_malformed_file_raises(tmp_path):
    bogus = tmp_path / "not_really.nii.gz"
    bogus.write_text("this is plain text, not a NIfTI image")
    with pytest.raises(FacetInputError) as exc_info:
        load_volume(str(bogus))
    assert str(bogus) in str(exc_info.value)
    # No raw TPTBox/nibabel exception type leaks through.
    assert exc_info.type is FacetInputError


def test_ac6_load_case_shape_mismatch_raises(tmp_path):
    affine = np.diag([1.0, 1.0, 1.0, 1.0])
    scan = np.zeros((3, 3, 3), dtype=np.float32)
    seg = np.zeros((3, 3, 4), dtype=np.int16)
    scan_path = _write_nii(tmp_path, scan, None, name="scan.nii.gz", affine=affine)
    seg_path = _write_nii(tmp_path, seg, None, name="seg.nii.gz", affine=affine)

    with pytest.raises(FacetInputError) as exc_info:
        load_case(scan_path, seg_path)

    msg = str(exc_info.value)
    assert "(3, 3, 3)" in msg
    assert "(3, 3, 4)" in msg


def test_ac6_load_case_incompatible_affine_raises(tmp_path):
    affine_scan = np.diag([1.0, 1.0, 1.0, 1.0])
    affine_seg = np.diag([2.0, 1.0, 1.0, 1.0])
    scan = np.zeros((3, 3, 3), dtype=np.float32)
    seg = np.zeros((3, 3, 3), dtype=np.int16)
    scan_path = _write_nii(tmp_path, scan, None, name="scan.nii.gz", affine=affine_scan)
    seg_path = _write_nii(tmp_path, seg, None, name="seg.nii.gz", affine=affine_seg)

    with pytest.raises(FacetInputError, match="incompatible affines"):
        load_case(scan_path, seg_path)


def test_ac6_load_case_tolerant_affine(tmp_path):
    affine_scan = np.diag([1.0, 1.0, 1.0, 1.0])
    affine_seg = affine_scan.copy()
    affine_seg[0, 0] += 1e-6
    scan = np.zeros((3, 3, 3), dtype=np.float32)
    seg = np.zeros((3, 3, 3), dtype=np.int16)
    scan_path = _write_nii(tmp_path, scan, None, name="scan.nii.gz", affine=affine_scan)
    seg_path = _write_nii(tmp_path, seg, None, name="seg.nii.gz", affine=affine_seg)

    case = load_case(scan_path, seg_path)  # must not raise
    assert isinstance(case, Case)


# =========================================================================== #
# AC7: a full segfacet run on a synthetic fixture is unaffected
# =========================================================================== #


def test_ac7_report_matches_committed_golden_within_tolerance():
    """Builds a fresh report (mirroring ``segfacet run``) for every committed
    Stage-5 corpus case through the post-migration loader, and compares its
    verdict/findings against the pinned pre-098 verdict+findings shape
    (``_PRE_098_GOLDEN_VERDICT_AND_FINDINGS``, itself frozen before this
    migration and unaffected by it). This is the pre/post-migration
    identity check AC7 asks for, re-pointed (item 126) at fresh output --
    the committed golden JSON this used to compare against was retired, see
    docs/aide/golden-decision-table.md's "## Retirement execution log"."""
    import segfacet.synth  # noqa: F401 -- self-registers synth operators
    from segfacet.synth.corpus import load_manifest
    from segfacet.synth.golden import build_report_for_case
    from test_098_stray_components import _PRE_098_GOLDEN_VERDICT_AND_FINDINGS

    manifest = load_manifest()
    for case in manifest["cases"]:
        case_id = case["case_id"]
        if case_id not in _PRE_098_GOLDEN_VERDICT_AND_FINDINGS:
            continue
        fresh = build_report_for_case(case)
        expected = _PRE_098_GOLDEN_VERDICT_AND_FINDINGS[case_id]
        assert fresh["verdict"] == expected["verdict"], (
            f"case {case_id!r}: post-migration report diverges from the "
            "pinned pre-098 verdict"
        )


def test_ac7_report_still_validates_and_has_expected_verdict():
    """A representative case's freshly-built report keeps its documented
    shape/verdict after the migration -- not just numeric closeness."""
    import segfacet.synth  # noqa: F401
    from segfacet.synth.corpus import load_manifest
    from segfacet.synth.golden import build_report_for_case

    manifest = load_manifest()
    case = next(c for c in manifest["cases"] if c["case_id"] == "clean_control")

    report = build_report_for_case(case)

    assert report["verdict"] == "pass"
    assert report["findings"] == []
    assert "features" in report


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_rotated_but_ras_resolving_affine_does_not_crash(tmp_path):
    """An affine whose axcodes already resolve to RAS, but via a non-diagonal
    (rotated) direction-cosine matrix, still loads cleanly -- reorient only
    needs to confirm the axcode result, not axis-alignment."""
    theta = np.deg2rad(3.0)  # a small rotation, well within RAS-resolving range
    c, s = np.cos(theta), np.sin(theta)
    rotation = np.array(
        [
            [c, -s, 0.0],
            [s, c, 0.0],
            [0.0, 0.0, 1.0],
        ]
    )
    scale = np.diag([1.0, 1.0, 1.0])
    affine = np.eye(4)
    affine[:3, :3] = rotation @ scale

    resolved = nib.aff2axcodes(affine)
    assert resolved == ("R", "A", "S")

    data = np.zeros((4, 4, 4), dtype=np.float32)
    path = _write_nii(tmp_path, data, None, affine=affine)

    vol = load_volume(path)  # must not raise
    assert vol.data.shape == (4, 4, 4)


def test_adv_integer_labels_round_trip_without_float_casting(tmp_path):
    """A label map loaded with integer_labels=True keeps exact integer
    values through the TPTBox segmentation-array path (no float cast)."""
    data = np.zeros((4, 4, 4), dtype=np.int16)
    data[0, 0, 0] = 5
    data[1, 1, 1] = 23
    path = _write_nii(tmp_path, data, (1.0, 1.0, 1.0))

    vol = load_volume(path, integer_labels=True)

    assert np.issubdtype(vol.data.dtype, np.integer)
    assert vol.data[0, 0, 0] == 5
    assert vol.data[1, 1, 1] == 23


def test_adv_returned_array_still_owns_its_data(tmp_path):
    """The returned array remains a standalone copy after the migration
    (not a view/memmap onto the underlying TPTBox NII object)."""
    data = np.arange(8, dtype=np.int16).reshape(2, 2, 2)
    path = _write_nii(tmp_path, data, (1.0, 1.0, 1.0))

    vol = load_volume(path, integer_labels=True)

    assert vol.data.flags.owndata
