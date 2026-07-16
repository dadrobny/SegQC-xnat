"""Stage-13 acceptance (item 088) — the committed VerSe19 descriptor + the full
``descriptor -> resolve -> build-reference / evaluate`` path.

The automated portion runs against a **synthetic VerSe-shaped stand-in** cohort
built in ``tmp_path`` (real tiny NIfTIs from the production synth builders, laid
out exactly like the committed ``verse19.yaml`` expects), driving the committed
descriptor with ``--data-root`` pointed at the stand-in. The **real** VerSe19
clause is gated on the ``SEGQC_VERSE_COHORT`` env var and **skips cleanly** when
the (uncommitted, large/licensed) cohort is absent — the common case, incl. CI.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import nibabel as nib
import pytest

from segqc.cli import main
from segqc.datasets import (
    DatasetDescriptor,
    bundled_descriptor_path,
    load_descriptor,
    resolve,
)
from segqc.synth.clean_gt import build_clean_spine
from segqc.synth.intensity import paint_clean_scan

VERSE19 = bundled_descriptor_path("verse19.yaml")
LEVELS = ("L1", "L2", "L3", "L4", "L5")


def real_verse_cohort_dir() -> "Path | None":
    """The real VerSe19 root from ``SEGQC_VERSE_COHORT`` iff set AND a directory,
    else ``None`` — the single runtime gate for the real-cohort clause (analogue
    of item 084's ``real_verse_cohort_dir`` / item 075's ``cupy_available``)."""
    raw = os.environ.get("SEGQC_VERSE_COHORT")
    if not raw:
        return None
    d = Path(raw)
    return d if d.is_dir() else None


requires_verse = pytest.mark.skipif(
    real_verse_cohort_dir() is None,
    reason="real VerSe19 cohort not mounted (set SEGQC_VERSE_COHORT to the VerSe19 root)",
)


def _standin_split(root: Path, subjects, *, split="training", with_scan=True):
    """Build a synthetic VerSe-shaped stand-in split under
    ``root/dataset-verse19<split>/`` matching the committed descriptor's layout."""
    base = root / f"dataset-verse19{split}"
    for i, sub in enumerate(subjects):
        spine = build_clean_spine(levels=LEVELS, spacing=(1.0, 1.0, 1.0), curve_amplitude_mm=4.0 + i)
        d = base / "derivatives" / sub
        d.mkdir(parents=True, exist_ok=True)
        nib.save(spine.seg_img, str(d / f"{sub}_seg-vert_msk.nii.gz"))
        if with_scan:
            r = base / "rawdata" / sub
            r.mkdir(parents=True, exist_ok=True)
            nib.save(paint_clean_scan(spine.seg_img, seed=i), str(r / f"{sub}_ct.nii.gz"))
    return root


# --------------------------------------------------------------------------- #
# The committed descriptor is well-formed
# --------------------------------------------------------------------------- #
def test_committed_verse19_descriptor_shape():
    d = load_descriptor(VERSE19)
    assert isinstance(d, DatasetDescriptor)
    assert d.label_convention == "default" and d.role == "gt"
    assert set(d.subsets) == {"training", "validation", "test"}
    assert d.subsets["training"] == {"root": "dataset-verse19training"}
    assert d.scan and "{id}" in d.scan


# --------------------------------------------------------------------------- #
# Synthetic stand-in: descriptor -> resolve, with split subjects + subsets
# --------------------------------------------------------------------------- #
def test_standin_resolve_subsets_and_triples(tmp_path):
    _standin_split(tmp_path, ["sub-verse004", "sub-verse005"], split="training")
    _standin_split(tmp_path, ["sub-verse099"], split="validation")
    # A split-subject mask (its own case; no matching CT -> scan None).
    dj = tmp_path / "dataset-verse19training" / "derivatives" / "sub-verse004"
    nib.save(
        build_clean_spine(levels=LEVELS).seg_img,
        str(dj / "sub-verse004_split-verse01_seg-vert_msk.nii.gz"),
    )

    d = load_descriptor(VERSE19)
    train = resolve(d, data_root=tmp_path, subset="training")
    val = resolve(d, data_root=tmp_path, subset="validation")

    assert train.case_ids == ("sub-verse004", "sub-verse004_split-verse01", "sub-verse005")
    assert val.case_ids == ("sub-verse099",)
    assert set(train.case_ids).isdisjoint(val.case_ids)  # held-out story
    # Regular subject resolves its CT; the split subject has no matching CT.
    by_id = {c.case_id: c for c in train}
    assert Path(by_id["sub-verse004"].scan_path).name == "sub-verse004_ct.nii.gz"
    assert by_id["sub-verse004_split-verse01"].scan_path is None


# --------------------------------------------------------------------------- #
# Synthetic stand-in: full CLI build-reference + evaluate via the descriptor
# --------------------------------------------------------------------------- #
def test_standin_build_reference_and_evaluate_cli(tmp_path):
    _standin_split(tmp_path, ["sub-verse004", "sub-verse005", "sub-verse006"], split="training")

    ref = tmp_path / "reference_verse_standin.json"
    rc = main([
        "build-reference", "--dataset-schema", str(VERSE19),
        "--data-root", str(tmp_path), "--subset", "training",
        "--out", str(ref), "--source", "verse-standin", "--build-date", "2026-07-16",
    ])
    assert rc == 0 and ref.exists()

    out = tmp_path / "eval"
    rc = main([
        "evaluate", "--dataset-schema", str(VERSE19),
        "--data-root", str(tmp_path), "--subset", "training",
        "--out", str(out), "--cohort-id", "verse-standin-training",
        "--build-date", "2026-07-16",
    ])
    assert rc == 0
    report = json.loads((out / "eval_report.json").read_text())
    fpr = report["metrics"]["false_positive_rate"]
    assert isinstance(fpr, float) and 0.0 <= fpr <= 1.0
    assert fpr == 0.0  # clean synthetic GT passes QC


# --------------------------------------------------------------------------- #
# The real-VerSe clause is a GENUINE skip when no cohort is mounted
# --------------------------------------------------------------------------- #
def test_real_verse_clause_is_genuine_skip():
    """Mirror test_069/test_075/test_084: the marker is a real skipif with a bool
    condition that is True on this (data-absent) host -- never xfail, never a
    vacuous pass."""
    assert requires_verse.mark.name == "skipif"
    assert isinstance(requires_verse.mark.args[0], bool)
    assert requires_verse.mark.args[0] is True


def test_real_verse_cohort_dir_env(monkeypatch, tmp_path):
    monkeypatch.delenv("SEGQC_VERSE_COHORT", raising=False)
    assert real_verse_cohort_dir() is None
    monkeypatch.setenv("SEGQC_VERSE_COHORT", str(tmp_path / "nope"))
    assert real_verse_cohort_dir() is None  # nonexistent path -> None, not a crash
    monkeypatch.setenv("SEGQC_VERSE_COHORT", str(tmp_path))
    assert real_verse_cohort_dir() == tmp_path


@requires_verse
def test_real_verse_resolves_training_split():
    """On a data-holding host, the committed descriptor resolves the real VerSe19
    training split to non-empty GT cases with existing seg files. Skips cleanly
    everywhere else."""
    root = real_verse_cohort_dir()
    d = load_descriptor(VERSE19)
    cohort = resolve(d, data_root=root, subset="training")
    assert len(cohort) > 0
    for case in cohort:
        assert case.role == "gt"
        assert Path(case.seg_path).exists()
        assert case.case_id.startswith("sub-verse")


# --------------------------------------------------------------------------- #
# Scope guard: no raw scans committed, only the descriptor
# --------------------------------------------------------------------------- #
def test_no_raw_data_committed_under_datasets():
    import segqc.datasets as ds

    pkg_dir = Path(ds.__file__).resolve().parent
    offending = [
        p.name
        for p in pkg_dir.rglob("*")
        if p.is_file()
        and "__pycache__" not in p.parts  # ignore gitignored build bytecode
        and p.suffix not in {".py", ".yaml", ".yml", ".json"}
    ]
    assert offending == [], f"unexpected non-descriptor files under segqc/datasets: {offending}"
