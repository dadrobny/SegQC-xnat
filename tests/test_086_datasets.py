"""Tests for item 086 -- the dataset-agnostic Cohort/Case interface, descriptor
schema, and resolver (``segqc.datasets``, Stage 13).

All fixtures are tiny synthetic directory trees built in ``tmp_path`` (empty
``.nii.gz`` files -- the resolver discovers files by layout, never reads voxels).
No real dataset is required.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from segqc.datasets import (
    ROLE_CANDIDATE,
    ROLE_GT,
    Case,
    Cohort,
    DatasetDescriptor,
    DatasetSchemaError,
    load_descriptor,
    resolve,
)
from segqc.labels import LabelConvention

# VerSe-shaped case-id regex reused across tests.
VERSE_ID = r"(?P<id>sub-verse\d+(?:_split-verse\d+)?)_seg-vert_msk\.nii\.gz$"


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    return path


def _nested_verse(root: Path, subjects, *, with_scan=True, split=None):
    """Build a VerSe-shaped nested tree under ``root``.

    ``subjects`` = iterable of ``sub-verseNNN`` ids; ``split`` = optional
    ``(subject, split_id)`` to add one split-subject mask.
    """
    for sub in subjects:
        _touch(root / "derivatives" / sub / f"{sub}_seg-vert_msk.nii.gz")
        if with_scan:
            _touch(root / "rawdata" / sub / f"{sub}_ct.nii.gz")
    if split is not None:
        sub, split_id = split
        cid = f"{sub}_split-{split_id}"
        _touch(root / "derivatives" / sub / f"{cid}_seg-vert_msk.nii.gz")
    return root


def _verse_descriptor(root: Path, **overrides) -> DatasetDescriptor:
    data = {
        "data_root": str(root),
        "seg": "derivatives/sub-*/**/*_seg-vert_msk.nii.gz",
        "case_id": VERSE_ID,
        "scan": "rawdata/{id}/{id}_ct.nii.gz",
    }
    data.update(overrides)
    return DatasetDescriptor.from_dict(data, descriptor_dir=str(root))


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
def test_case_and_cohort_shape():
    conv = LabelConvention.default()
    c1 = Case("b", "b_seg.nii.gz", None, ROLE_GT, conv)
    c0 = Case("a", "a_seg.nii.gz", "a_scan.nii.gz", ROLE_GT, conv, {"k": "v"})
    cohort = Cohort(cases=(c0, c1), name="training")
    assert len(cohort) == 2
    assert [c.case_id for c in cohort] == ["a", "b"]  # iterable
    assert cohort.case_ids == ("a", "b")
    assert c0.scan_path == "a_scan.nii.gz" and c1.scan_path is None
    assert c0.role == ROLE_GT and c0.metadata == {"k": "v"}


# --------------------------------------------------------------------------- #
# Descriptor validation
# --------------------------------------------------------------------------- #
def test_descriptor_requires_keys_and_id_group():
    with pytest.raises(DatasetSchemaError, match="missing required key"):
        DatasetDescriptor.from_dict({"data_root": "/x", "seg": "*.nii.gz"})
    with pytest.raises(DatasetSchemaError, match="named group"):
        DatasetDescriptor.from_dict(
            {"data_root": "/x", "seg": "*.nii.gz", "case_id": r"(\d+)_seg"}
        )
    with pytest.raises(DatasetSchemaError, match="not a valid regex"):
        DatasetDescriptor.from_dict(
            {"data_root": "/x", "seg": "*.nii.gz", "case_id": r"(?P<id>("}
        )


def test_descriptor_rejects_unknown_key_role_convention():
    base = {"data_root": "/x", "seg": "*.nii.gz", "case_id": r"(?P<id>.+)_seg"}
    with pytest.raises(DatasetSchemaError, match="unknown key"):
        DatasetDescriptor.from_dict({**base, "bogus": 1})
    with pytest.raises(DatasetSchemaError, match="role"):
        DatasetDescriptor.from_dict({**base, "role": "reference"})
    with pytest.raises(DatasetSchemaError, match="label_convention"):
        DatasetDescriptor.from_dict({**base, "label_convention": "acme"})


def test_descriptor_defaults():
    d = DatasetDescriptor.from_dict(
        {"data_root": "/x", "seg": "*.nii.gz", "case_id": r"(?P<id>.+)_seg"}
    )
    assert d.role == ROLE_GT and d.label_convention == "default" and d.scan is None
    assert d.subsets == {}


# --------------------------------------------------------------------------- #
# load_descriptor (YAML / JSON)
# --------------------------------------------------------------------------- #
def test_load_descriptor_yaml_and_errors(tmp_path):
    p = tmp_path / "verse.yaml"
    p.write_text(
        "data_root: /data/verse\n"
        'seg: "derivatives/**/*_msk.nii.gz"\n'
        'case_id: "(?P<id>sub-\\\\d+)_msk"\n',
        encoding="utf-8",
    )
    d = load_descriptor(p)
    assert d.data_root == "/data/verse"
    assert d.descriptor_dir == str(tmp_path.resolve())

    with pytest.raises(DatasetSchemaError, match="not found"):
        load_descriptor(tmp_path / "nope.yaml")
    bad = tmp_path / "bad.yaml"
    bad.write_text("data_root: [unclosed\n", encoding="utf-8")
    with pytest.raises(DatasetSchemaError, match="valid YAML"):
        load_descriptor(bad)


# --------------------------------------------------------------------------- #
# Resolution: nested (VerSe-shaped)
# --------------------------------------------------------------------------- #
def test_resolve_nested_triples_and_order(tmp_path):
    root = _nested_verse(tmp_path, ["sub-verse007", "sub-verse004", "sub-verse005"])
    cohort = resolve(_verse_descriptor(root))
    assert cohort.case_ids == ("sub-verse004", "sub-verse005", "sub-verse007")  # sorted
    c = cohort.cases[0]
    assert c.case_id == "sub-verse004"
    assert Path(c.seg_path).name == "sub-verse004_seg-vert_msk.nii.gz"
    assert Path(c.scan_path).name == "sub-verse004_ct.nii.gz"
    assert Path(c.seg_path).is_absolute() and Path(c.scan_path).is_absolute()
    assert c.role == ROLE_GT
    assert c.label_convention.name_of(20) == LabelConvention.default().name_of(20)
    # Determinism: a second resolve yields identical triples.
    again = resolve(_verse_descriptor(root))
    assert cohort.case_ids == again.case_ids


def test_resolve_missing_scan_is_none(tmp_path):
    root = _nested_verse(tmp_path, ["sub-verse004"], with_scan=False)
    cohort = resolve(_verse_descriptor(root))
    assert len(cohort) == 1
    assert cohort.cases[0].scan_path is None


def test_resolve_split_subject_case_id(tmp_path):
    root = _nested_verse(tmp_path, ["sub-verse004"], split=("sub-verse004", "verse01"))
    cohort = resolve(_verse_descriptor(root))
    assert "sub-verse004" in cohort.case_ids
    assert "sub-verse004_split-verse01" in cohort.case_ids  # split is its own case


def test_resolve_seg_only_descriptor(tmp_path):
    root = _nested_verse(tmp_path, ["sub-verse004"], with_scan=False)
    cohort = resolve(_verse_descriptor(root, scan=None))
    assert cohort.cases[0].scan_path is None


# --------------------------------------------------------------------------- #
# Resolution: flat layout (back-compat shape)
# --------------------------------------------------------------------------- #
def test_resolve_flat_layout(tmp_path):
    _touch(tmp_path / "caseA_seg.nii.gz")
    _touch(tmp_path / "caseA_scan.nii.gz")
    _touch(tmp_path / "caseB_seg.nii.gz")
    d = DatasetDescriptor.from_dict(
        {
            "data_root": str(tmp_path),
            "seg": "*_seg.nii.gz",
            "case_id": r"(?P<id>.+)_seg\.nii\.gz$",
            "scan": "{id}_scan.nii.gz",
        }
    )
    cohort = resolve(d)
    assert cohort.case_ids == ("caseA", "caseB")
    assert Path(cohort.cases[0].scan_path).name == "caseA_scan.nii.gz"
    assert cohort.cases[1].scan_path is None


# --------------------------------------------------------------------------- #
# data_root override + role override
# --------------------------------------------------------------------------- #
def test_data_root_override_and_role_override(tmp_path):
    root = _nested_verse(tmp_path / "elsewhere", ["sub-verse004"])
    # Descriptor points at a bogus root; override at resolve time.
    d = _verse_descriptor(Path("/does/not/exist"), role=ROLE_GT)
    cohort = resolve(d, data_root=root, role=ROLE_CANDIDATE)
    assert cohort.case_ids == ("sub-verse004",)
    assert cohort.cases[0].role == ROLE_CANDIDATE

    with pytest.raises(DatasetSchemaError, match="role"):
        resolve(d, data_root=root, role="bogus")


# --------------------------------------------------------------------------- #
# Subsets: root (folder split), ids, csv, glob
# --------------------------------------------------------------------------- #
def test_subset_root_folder_split(tmp_path):
    _nested_verse(tmp_path / "dataset-verse19training", ["sub-verse004", "sub-verse005"])
    _nested_verse(tmp_path / "dataset-verse19validation", ["sub-verse099"])
    d = _verse_descriptor(
        tmp_path,
        subsets={
            "training": {"root": "dataset-verse19training"},
            "validation": {"root": "dataset-verse19validation"},
        },
    )
    train = resolve(d, subset="training")
    val = resolve(d, subset="validation")
    assert train.case_ids == ("sub-verse004", "sub-verse005")
    assert val.case_ids == ("sub-verse099",)
    assert train.name == "training"
    # Disjoint subsets -> the "held-out" story the framework never has to know about.
    assert set(train.case_ids).isdisjoint(val.case_ids)


def test_subset_ids_and_glob(tmp_path):
    root = _nested_verse(tmp_path, ["sub-verse004", "sub-verse005", "sub-verse006"])
    d = _verse_descriptor(
        root,
        subsets={
            "picked": {"ids": ["sub-verse004", "sub-verse006"]},
            "evens": {"glob": "*4"},
        },
    )
    assert resolve(d, subset="picked").case_ids == ("sub-verse004", "sub-verse006")
    assert resolve(d, subset="evens").case_ids == ("sub-verse004",)


def test_subset_csv(tmp_path):
    root = _nested_verse(tmp_path, ["sub-verse004", "sub-verse005", "sub-verse006"])
    csv_path = tmp_path / "heldout.csv"
    csv_path.write_text("case_id,note\nsub-verse005,x\nsub-verse006,y\n", encoding="utf-8")
    d = _verse_descriptor(root, subsets={"heldout": {"csv": "heldout.csv"}})
    # descriptor_dir is tmp_path (set by _verse_descriptor), so the relative CSV resolves.
    assert resolve(d, subset="heldout").case_ids == ("sub-verse005", "sub-verse006")


def test_unknown_subset_raises(tmp_path):
    root = _nested_verse(tmp_path, ["sub-verse004"])
    with pytest.raises(DatasetSchemaError, match="unknown subset"):
        resolve(_verse_descriptor(root), subset="nope")


# --------------------------------------------------------------------------- #
# Adversarial
# --------------------------------------------------------------------------- #
def test_case_id_regex_no_match_raises(tmp_path):
    root = _nested_verse(tmp_path, ["sub-verse004"])
    d = _verse_descriptor(root, case_id=r"(?P<id>NOPE\d+)_seg-vert_msk\.nii\.gz$")
    with pytest.raises(DatasetSchemaError, match="did not match"):
        resolve(d)


def test_duplicate_case_id_raises(tmp_path):
    # Two seg files under different (both sub-*-matching) subdirs collapsing to
    # the same case_id.
    _touch(tmp_path / "derivatives" / "sub-verse004" / "sub-verse004_seg-vert_msk.nii.gz")
    _touch(tmp_path / "derivatives" / "sub-verse004b" / "sub-verse004_seg-vert_msk.nii.gz")
    with pytest.raises(DatasetSchemaError, match="duplicate case_id"):
        resolve(_verse_descriptor(tmp_path))


def test_empty_dataset_is_empty_cohort(tmp_path):
    (tmp_path / "derivatives").mkdir()
    cohort = resolve(_verse_descriptor(tmp_path))
    assert len(cohort) == 0 and cohort.case_ids == ()
