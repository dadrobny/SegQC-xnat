"""Tests for item 087 -- the Cohort-driven ingestion/manifest path and the CLI
``--dataset-schema`` / ``--data-root`` / ``--subset`` flags on
``run`` / ``build-reference`` / ``evaluate`` (Stage 13).

Fixtures are real (tiny) synthetic NIfTIs built with the production synth
builders, arranged both flat (item-044 convention) and nested (VerSe-shaped),
so a nested descriptor build can be checked for parity against a flat build over
the same subjects. No real dataset is required.
"""
from __future__ import annotations

import json
from pathlib import Path

import nibabel as nib
import pytest

from segqc.cli import main
from segqc.datasets import resolve, load_descriptor
from segqc.reference import build_reference, build_reference_from_cohort, load_artifact
from segqc.reference.ingest import ingest_cohort, ingest_dataset_cohort
from segqc.synth.clean_gt import build_clean_spine
from segqc.synth.intensity import paint_clean_scan

SUBJECTS = ("sub-verse004", "sub-verse005", "sub-verse006")
LEVELS = ("L1", "L2", "L3", "L4", "L5")


def _seg_and_scan(seed: int):
    spine = build_clean_spine(levels=LEVELS, spacing=(1.0, 1.0, 1.0), curve_amplitude_mm=4.0 + seed)
    scan = paint_clean_scan(spine.seg_img, seed=seed)
    return spine.seg_img, scan


def _build_flat(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    for i, sub in enumerate(SUBJECTS):
        seg, scan = _seg_and_scan(i)
        nib.save(seg, str(root / f"{sub}_seg.nii.gz"))
        nib.save(scan, str(root / f"{sub}_scan.nii.gz"))
    return root


def _build_nested(root: Path):
    for i, sub in enumerate(SUBJECTS):
        seg, scan = _seg_and_scan(i)
        d = root / "derivatives" / sub
        r = root / "rawdata" / sub
        d.mkdir(parents=True, exist_ok=True)
        r.mkdir(parents=True, exist_ok=True)
        nib.save(seg, str(d / f"{sub}_seg-vert_msk.nii.gz"))
        nib.save(scan, str(r / f"{sub}_ct.nii.gz"))
    return root


def _write_descriptor(path: Path, data_root: Path, *, subsets_block: str = "") -> Path:
    path.write_text(
        f'data_root: "{data_root}"\n'
        'seg: "derivatives/sub-*/**/*_seg-vert_msk.nii.gz"\n'
        'case_id: "(?P<id>sub-verse\\\\d+(?:_split-verse\\\\d+)?)_seg-vert_msk\\\\.nii\\\\.gz$"\n'
        'scan: "rawdata/{id}/{id}_ct.nii.gz"\n'
        + subsets_block,
        encoding="utf-8",
    )
    return path


# --------------------------------------------------------------------------- #
# ingest parity: Cohort-driven vs flat, same subjects
# --------------------------------------------------------------------------- #
def test_ingest_dataset_cohort_matches_flat_records(tmp_path):
    flat = _build_flat(tmp_path / "flat")
    nested = _build_nested(tmp_path / "nested")
    desc = load_descriptor(_write_descriptor(tmp_path / "d.yaml", nested))
    cohort = resolve(desc)

    flat_ing = ingest_cohort(flat, with_intensity=True, with_morphology=True)
    cohort_ing = ingest_dataset_cohort(cohort, with_intensity=True, with_morphology=True)

    # Same subject ids in both layouts (flat stem == nested case_id), so records
    # match per (subject, level) -- byte-identical seg/scan images in both trees.
    assert len(cohort_ing.records) == len(flat_ing.records) > 0
    flat_by = {(r.subject_id, r.level_name): dict(r.features) for r in flat_ing.records}
    for rec in cohort_ing.records:
        key = (rec.subject_id, rec.level_name)
        assert set(rec.features) == set(flat_by[key])
        for k in rec.features:
            assert rec.features[k] == pytest.approx(flat_by[key][k])


def test_build_reference_from_cohort_matches_flat(tmp_path):
    flat = _build_flat(tmp_path / "flat")
    nested = _build_nested(tmp_path / "nested")
    cohort = resolve(load_descriptor(_write_descriptor(tmp_path / "d.yaml", nested)))

    ref_flat = build_reference(flat, source="s", build_date="2026-07-16")
    ref_nested = build_reference_from_cohort(cohort, source="s", build_date="2026-07-16")

    assert set(ref_flat.levels) == set(ref_nested.levels)
    for level in ref_flat.levels:
        fa = ref_flat.levels[level]["all"].feature_stats
        na = ref_nested.levels[level]["all"].feature_stats
        assert set(fa) == set(na)
        for name in fa:
            assert na[name].mean == pytest.approx(fa[name].mean)
            assert na[name].count == fa[name].count


# --------------------------------------------------------------------------- #
# CLI: build-reference --dataset-schema
# --------------------------------------------------------------------------- #
def test_cli_build_reference_dataset_schema(tmp_path):
    nested = _build_nested(tmp_path / "nested")
    desc = _write_descriptor(tmp_path / "d.yaml", nested)
    out = tmp_path / "ref.json"
    rc = main(["build-reference", "--dataset-schema", str(desc), "--out", str(out),
               "--source", "verse-test", "--build-date", "2026-07-16"])
    assert rc == 0
    art = load_artifact(out)
    assert art.provenance.source == "verse-test"
    assert set(LEVELS).issubset(set(art.levels))


def test_cli_build_reference_mutually_exclusive(tmp_path, capsys):
    nested = _build_nested(tmp_path / "nested")
    desc = _write_descriptor(tmp_path / "d.yaml", nested)
    out = tmp_path / "ref.json"
    # Both given -> error, no file.
    rc = main(["build-reference", "--cohort", str(nested), "--dataset-schema", str(desc),
               "--out", str(out)])
    assert rc == 1
    assert "exactly one" in capsys.readouterr().err
    assert not out.exists()
    # Neither given -> error.
    rc = main(["build-reference", "--out", str(out)])
    assert rc == 1


def test_cli_build_reference_data_root_override(tmp_path):
    nested = _build_nested(tmp_path / "nested")
    # Descriptor points at a bogus root; override at the CLI.
    desc = _write_descriptor(tmp_path / "d.yaml", Path("/does/not/exist"))
    out = tmp_path / "ref.json"
    rc = main(["build-reference", "--dataset-schema", str(desc), "--data-root", str(nested),
               "--out", str(out), "--source", "s", "--build-date", "2026-07-16"])
    assert rc == 0 and out.exists()


# --------------------------------------------------------------------------- #
# CLI: build-reference --subset (folder split)
# --------------------------------------------------------------------------- #
def test_cli_build_reference_subset(tmp_path):
    root = tmp_path / "verse"
    _build_nested(root / "dataset-verse19training")
    desc = _write_descriptor(
        tmp_path / "d.yaml", root,
        subsets_block='subsets:\n  training:\n    root: "dataset-verse19training"\n',
    )
    out = tmp_path / "ref.json"
    rc = main(["build-reference", "--dataset-schema", str(desc), "--subset", "training",
               "--out", str(out), "--source", "s", "--build-date", "2026-07-16"])
    assert rc == 0 and out.exists()


# --------------------------------------------------------------------------- #
# CLI: evaluate --dataset-schema  (GT-as-expected-pass -> FPR)
# --------------------------------------------------------------------------- #
def test_cli_evaluate_dataset_schema_fpr(tmp_path):
    nested = _build_nested(tmp_path / "nested")
    desc = _write_descriptor(tmp_path / "d.yaml", nested)
    out = tmp_path / "eval"
    rc = main(["evaluate", "--dataset-schema", str(desc), "--out", str(out),
               "--cohort-id", "verse-standin", "--build-date", "2026-07-16"])
    assert rc == 0
    report = json.loads((out / "eval_report.json").read_text())
    fpr = report["metrics"]["false_positive_rate"]
    assert isinstance(fpr, float) and 0.0 <= fpr <= 1.0
    assert fpr == 0.0  # clean synthetic GT should pass QC


def test_cli_evaluate_mutually_exclusive(tmp_path, capsys):
    rc = main(["evaluate", "--out", str(tmp_path / "eval")])
    assert rc == 1
    assert "exactly one" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# CLI: run --dataset-schema  (batch)
# --------------------------------------------------------------------------- #
def test_cli_run_dataset_schema_batch(tmp_path):
    nested = _build_nested(tmp_path / "nested")
    desc = _write_descriptor(tmp_path / "d.yaml", nested)
    out = tmp_path / "runs"
    rc = main(["run", "--dataset-schema", str(desc), "--out", str(out)])
    assert rc == 0
    for sub in SUBJECTS:
        assert (out / sub / "segqc_report.json").exists()
        assert (out / sub / "segqc_report.txt").exists()


def test_cli_run_requires_scan_seg_or_schema(tmp_path, capsys):
    rc = main(["run", "--out", str(tmp_path / "o")])
    assert rc == 1
    assert "--scan and --seg" in capsys.readouterr().err
