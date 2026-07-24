"""Tests for the AIDE project-status report generator (scripts/aide_status_report.py).

This is a dev/process tool, not part of the shipped ``segfacet`` package, but its
parsing and rendering functions are pure and worth locking down so the living
status page stays trustworthy as the AIDE documents evolve.
"""
from __future__ import annotations

import datetime as _dt
import importlib.util
import sys
from pathlib import Path

# Load the script by path (it lives in scripts/, not on the package path). The
# module must be registered in sys.modules before exec so dataclass field
# introspection (which looks up cls.__module__) works under `from __future__
# import annotations`.
_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "aide_status_report.py"
_spec = importlib.util.spec_from_file_location("aide_status_report", _MODULE_PATH)
asr = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = asr
_spec.loader.exec_module(asr)  # type: ignore[union-attr]


PROGRESS_SAMPLE = """# Progress

| Stage | Title | Objectives | Status |
|-------|-------|-----------|--------|
| 0 | Scaffolding | (foundation) | 📋 |
| 2 | Feature Extraction | (core) | ✅ |
| 4 | Rule Engine | G2 | 🚧 |

| Objective | Delivered by | Status |
|-----------|--------------|--------|
| G1 Detect empty | Stage 1 | 📋 |
| G2 Failure modes | Stages 4, 5 | 🚧 |

## Stage 2 — Feature Extraction — ✅

- ✅ Per-label features. *(Item 011)*
- ✅ Connected components. *(Item 012)*

## Stage 4 — Rule Engine — 🚧

- ✅ Rule engine core. *(Item 026)*
- 📋 Coverage rules. *(Item 029)*
"""


def test_parse_progress_extracts_stages_and_statuses():
    stages, objectives, item_status = asr.parse_progress(PROGRESS_SAMPLE)

    by_num = {s.number: s for s in stages}
    assert by_num["0"].status == "planned"
    assert by_num["2"].status == "complete"
    assert by_num["4"].status == "in-progress"
    assert by_num["4"].title == "Rule Engine"

    codes = {o.code: o for o in objectives}
    assert codes["G1"].status == "planned"
    assert codes["G2"].delivered_by == "Stages 4, 5"

    # Items pick up their line status and the stage section they appear under.
    assert item_status[11] == ("complete", "2")
    assert item_status[26] == ("complete", "4")
    assert item_status[29] == ("planned", "4")


def test_parse_progress_status_precedence():
    text = (
        "## Stage 3 — X — 🚧\n"
        "- 📋 first mention. *(Item 050)*\n"
        "- ✅ later mention. *(Item 050)*\n"
    )
    _, _, item_status = asr.parse_progress(text)
    # The most-advanced status wins regardless of order.
    assert item_status[50][0] == "complete"


def test_parse_progress_item_ref_on_wrapped_continuation_line():
    # A deliverable that wraps leaves its *(Item NNN)* ref on a continuation
    # line with no icon; it must inherit the bullet's status, not default to
    # "planned". (Regression: items 001/004 wrongly shown as planned.)
    text = (
        "## Stage 0 — Scaffolding — ✅\n"
        "- ✅ Python package `segfacet/` targeting Python 3.9+; with pinned\n"
        "  core deps (NumPy, SciPy, scikit-image). *(Item 001)*\n"
        "- ✅ CLI entry point. *(Item 006)*\n"
    )
    _, _, item_status = asr.parse_progress(text)
    assert item_status[1] == ("complete", "0")
    assert item_status[6] == ("complete", "0")


def test_parse_progress_handles_empty():
    stages, objectives, item_status = asr.parse_progress("")
    assert stages == [] and objectives == [] and item_status == {}


def test_parse_items_reads_titles(tmp_path: Path):
    items = tmp_path / "items"
    items.mkdir()
    (items / "027-level-aware-bounds.md").write_text(
        "# Work Item 027: Level-aware bounds rules\n\nBody.", encoding="utf-8"
    )
    (items / "028-fragmentation-island.md").write_text(
        "Some preamble\n# 028 Fragmentation and island rules\n", encoding="utf-8"
    )
    titles = asr.parse_items(items)
    assert titles[27] == "Level-aware bounds rules"
    assert 28 in titles  # title resolved from heading or filename slug


def test_parse_items_missing_dir_returns_empty(tmp_path: Path):
    assert asr.parse_items(tmp_path / "nope") == {}


def test_parse_queues_collects_ordered_unique_numbers(tmp_path: Path):
    qdir = tmp_path / "queue"
    qdir.mkdir()
    (qdir / "queue-001.md").write_text(
        "### Item 026: core\n### Item 027: bounds\n", encoding="utf-8"
    )
    (qdir / "queue-002.md").write_text(
        "### Item 027: dup\n### Item 034: aggregate\n", encoding="utf-8"
    )
    assert asr.parse_queues(qdir) == [26, 27, 34]


def test_summarise_tests_counts_functions(tmp_path: Path):
    tdir = tmp_path / "tests"
    tdir.mkdir()
    (tdir / "test_a.py").write_text(
        "def test_one():\n    pass\n\ndef test_two():\n    pass\n", encoding="utf-8"
    )
    (tdir / "test_b.py").write_text("def test_three():\n    pass\n", encoding="utf-8")
    (tdir / "helper.py").write_text("def test_ignored():\n    pass\n", encoding="utf-8")
    summary = asr.summarise_tests(tdir)
    assert summary.file_count == 2
    assert summary.test_count == 3
    assert not summary.has_outcomes


def test_summarise_tests_with_junit(tmp_path: Path):
    tdir = tmp_path / "tests"
    tdir.mkdir()
    (tdir / "test_a.py").write_text("def test_one():\n    pass\n", encoding="utf-8")
    junit = tmp_path / "results.xml"
    junit.write_text(
        '<testsuite tests="10" failures="2" errors="1" skipped="1"></testsuite>',
        encoding="utf-8",
    )
    summary = asr.summarise_tests(tdir, junit)
    assert summary.has_outcomes
    assert summary.passed == 6
    assert summary.failed == 2
    assert summary.errors == 1
    assert summary.skipped == 1


def _model():
    return asr.build_report_model(
        aide_dir=asr.AIDE_DIR,
        now=_dt.datetime(2026, 7, 1, 12, 0, tzinfo=_dt.timezone.utc),
    )


def test_build_report_model_on_real_docs():
    model = _model()
    # The real progress.md has stages and objectives.
    assert model.stages, "expected roadmap stages parsed from progress.md"
    assert any(o.code == "G2" for o in model.objectives)
    # Known-complete items should be classified complete.
    complete = {i.number for i in model.items if i.status == "complete"}
    assert 26 in complete  # rule-engine core is done
    assert model.tests.file_count > 0


def test_render_html_is_self_contained_and_escaped():
    model = _model()
    doc = asr.render_html(model)
    assert doc.startswith("<!DOCTYPE html>")
    assert "<style>" in doc  # inline CSS, no external assets
    assert "http://" not in doc and "https://" not in doc  # no external fetches
    # Core sections present.
    for anchor in ("Work-Queue Overview", "Roadmap Phases",
                   "Vision Objective Coverage", "Reference Feature Distributions",
                   "Testing Overview", "Project Feature Highlights"):
        assert anchor in doc
    # Extension-point placeholders render when no images are supplied.
    assert "Extension point" in doc


def test_render_html_deterministic():
    a = asr.render_html(_model())
    b = asr.render_html(_model())
    assert a == b


def test_render_escapes_untrusted_titles():
    model = asr.ReportModel(generated_at="now")
    model.items.append(asr.WorkItem(number=1, title="<script>alert(1)</script>", status="planned"))
    doc = asr.render_html(model)
    assert "<script>alert(1)</script>" not in doc
    assert "&lt;script&gt;" in doc


def test_highlights_populate_when_images_supplied(tmp_path: Path):
    img_dir = tmp_path / "qc"
    img_dir.mkdir()
    # A 1x1 PNG.
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000a49444154789c6360000002000154a24f5f0000000049454e44ae426082"
    )
    (img_dir / "case01_sagittal.png").write_bytes(png)
    model = asr.build_report_model(qc_images_dir=img_dir, embed_images=True)
    assert model.qc_images
    doc = asr.render_html(model)
    assert "data:image/png;base64," in doc


CORPUS_SAMPLE = """{
  "manifest_version": 1,
  "cases": [
    {"case_id": "mode2_fragment", "failure_mode": 2, "failure_mode_name": "over/under-seg",
     "detection": "pipeline", "perturbation": "fragment", "expected_verdict": "fail",
     "expected_rule_ids": ["fragmentation"]},
    {"case_id": "clean_control", "failure_mode": 0, "failure_mode_name": "clean control",
     "detection": "pipeline", "perturbation": "identity", "expected_verdict": "pass",
     "expected_rule_ids": []},
    {"case_id": "mode8_force_overlap", "failure_mode": 8, "failure_mode_name": "overlap",
     "detection": "reconstructed_record", "perturbation": "force_overlap",
     "expected_verdict": "flagged-for-review", "expected_rule_ids": ["overlap"]}
  ]
}"""


def test_parse_corpus_manifest_reads_and_sorts_cases(tmp_path: Path):
    path = tmp_path / "manifest.json"
    path.write_text(CORPUS_SAMPLE, encoding="utf-8")
    cases = asr.parse_corpus_manifest(path)
    assert [c.failure_mode for c in cases] == [0, 2, 8]  # sorted by mode
    clean = cases[0]
    assert clean.case_id == "clean_control" and clean.expected_verdict == "pass"
    recon = cases[-1]
    assert recon.detection == "reconstructed_record"
    assert recon.expected_rule_ids == ["overlap"]


def test_parse_corpus_manifest_missing_returns_empty(tmp_path: Path):
    assert asr.parse_corpus_manifest(tmp_path / "nope.json") == []


def test_parse_corpus_manifest_malformed_returns_empty(tmp_path: Path):
    path = tmp_path / "manifest.json"
    path.write_text("{ not valid json ", encoding="utf-8")
    assert asr.parse_corpus_manifest(path) == []


def test_render_corpus_section_placeholder_when_absent():
    model = asr.ReportModel(generated_at="now")  # no corpus
    doc = asr.render_html(model)
    assert "Synthetic Failure Corpus" in doc
    assert "Extension point" in doc


def test_render_corpus_section_populated_shows_coverage_and_badges():
    model = asr.ReportModel(generated_at="now")
    model.corpus = [
        asr.CorpusCase("clean_control", 0, "clean control", "pipeline", "identity", "pass", []),
        asr.CorpusCase("mode8_force_overlap", 8, "overlap", "reconstructed_record",
                       "force_overlap", "flagged-for-review", ["overlap"]),
    ]
    doc = asr.render_html(model)
    assert "Synthetic Failure Corpus" in doc
    assert "mode8_force_overlap" in doc
    assert "reconstructed_record" in doc
    assert "1/8" in doc  # one non-clean §6 mode covered
    assert 'class="badge b-complete">pass' in doc  # verdict badge for pass


def test_long_finished_listing_is_collapsible():
    model = asr.ReportModel(generated_at="now")
    for n in range(asr._FOLD_THRESHOLD + 5):
        model.items.append(asr.WorkItem(number=n, title=f"Item {n}", status="complete"))
    doc = asr.render_html(model)
    assert 'details class="fold"' in doc
    assert "Finished work items (" in doc


def test_short_finished_listing_is_not_collapsed():
    model = asr.ReportModel(generated_at="now")
    model.items.append(asr.WorkItem(number=1, title="Only one", status="complete"))
    doc = asr.render_html(model)
    assert "<h3>Finished work items</h3>" in doc


def test_main_writes_output(tmp_path: Path):
    out = tmp_path / "status.html"
    rc = asr.main(["--out", str(out)])
    assert rc == 0
    assert out.is_file()
    assert out.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")


# --------------------------------------------------------------------------- #
# Phase grouping
# --------------------------------------------------------------------------- #

_PROGRESS_WITH_PHASES = """# Progress

| Stage | Title | Objectives | Status |
|-------|-------|-----------|--------|
| 0 | Scaffolding | (foundation) | ✅ |
| 7 | Evaluation | G3 | ✅ |
| 8 | Radiomics | (Phase 2) | ✅ |
| 10 | GPU | G6 | 📋 |

# Phase 1 — Complete MVP Pipeline

## Stage 0 — Scaffolding — ✅
## Stage 7 — Evaluation — ✅

# Phase 2 — Extensions

## Stage 8 — Radiomics — ✅
## Stage 10 — GPU — 📋
"""


def test_parse_phases_maps_stages_to_phases():
    phases, stage_to_phase = asr.parse_phases(_PROGRESS_WITH_PHASES)
    assert [(p.number, p.title) for p in phases] == [
        ("1", "Complete MVP Pipeline"),
        ("2", "Extensions"),
    ]
    assert stage_to_phase == {"0": "1", "7": "1", "8": "2", "10": "2"}


def test_stage_section_groups_by_phase_when_available():
    stages = [
        asr.Stage("0", "Scaffolding", "(foundation)", "complete", phase="1"),
        asr.Stage("8", "Radiomics", "(Phase 2)", "complete", phase="2"),
        asr.Stage("10", "GPU", "G6", "planned", phase="2"),
    ]
    model = asr.ReportModel(
        generated_at="now",
        phases=[asr.Phase("1", "Complete MVP Pipeline"), asr.Phase("2", "Extensions")],
        stages=stages,
    )
    html_out = asr._render_stage_section(model)
    assert "Phase 1 — Complete MVP Pipeline" in html_out
    assert "Phase 2 — Extensions" in html_out
    # Overall progress reflects all stages (1 of 3 not counted as complete).
    assert "2 of 3 roadmap stages complete" in html_out


def test_stage_section_falls_back_to_flat_table_without_phases():
    stages = [asr.Stage("0", "Scaffolding", "(foundation)", "complete")]
    model = asr.ReportModel(generated_at="now", phases=[], stages=stages)
    html_out = asr._render_stage_section(model)
    assert "Scaffolding" in html_out
    assert "Phase 1" not in html_out


# --------------------------------------------------------------------------- #
# Reference-distribution artifact (VerSe)
# --------------------------------------------------------------------------- #

_REFERENCE_SAMPLE = {
    "schema_version": "1.2",
    "subject_count": 5,
    "features": ["physical_volume_mm3", "extent_x_mm", "intensity_mean"],
    "percentiles": [1, 5, 25, 50, 75, 95, 99],
    "strata": ["all"],
    "provenance": {
        "source": "synthetic-verse-cohort",
        "build_date": "2026-07-11",
        "size_proxy_name": None,
    },
    "levels": {
        "L1": {
            "all": {
                "level_name": "L1",
                "stratum": "all",
                "record_count": 4,
                "feature_stats": {
                    "physical_volume_mm3": {
                        "count": 4, "mean": 19141.19, "std": 425.7,
                        "min": 18750.0, "max": 19714.7,
                        "percentiles": {"p50": 19050.0},
                    },
                    "extent_x_mm": {
                        "count": 4, "mean": 25.0, "std": 0.1,
                        "min": 25.0, "max": 25.3, "percentiles": {"p50": 25.0},
                    },
                    "intensity_mean": {
                        "count": 4, "mean": 210.0, "std": 5.0,
                        "min": 205.0, "max": 215.0, "percentiles": {"p50": 210.0},
                    },
                },
            }
        }
    },
}


def _write_reference(tmp_path: Path) -> Path:
    import json
    path = tmp_path / "reference_default.json"
    path.write_text(json.dumps(_REFERENCE_SAMPLE), encoding="utf-8")
    return path


def test_parse_reference_artifact_reads_provenance_and_stats(tmp_path: Path):
    ref = asr.parse_reference_artifact(_write_reference(tmp_path))
    assert ref is not None
    assert ref.source == "synthetic-verse-cohort"
    assert ref.subject_count == 5
    assert ref.is_synthetic is True
    assert ref.levels == ["L1"]
    assert ref.geometric_feature_count == 2  # physical_volume_mm3, extent_x_mm
    assert ref.intensity_feature_count == 1  # intensity_mean
    assert ref.level_stats["L1"]["physical_volume_mm3"]["mean"] == 19141.19


def test_parse_reference_artifact_missing_returns_none(tmp_path: Path):
    assert asr.parse_reference_artifact(tmp_path / "nope.json") is None


def test_parse_reference_artifact_malformed_returns_none(tmp_path: Path):
    bad = tmp_path / "reference_default.json"
    bad.write_text("{ not json", encoding="utf-8")
    assert asr.parse_reference_artifact(bad) is None


def test_reference_section_flags_synthetic_cohort_and_shows_matrix(tmp_path: Path):
    ref = asr.parse_reference_artifact(_write_reference(tmp_path))
    model = asr.ReportModel(generated_at="now", reference=ref)
    html_out = asr._render_reference_section(model)
    assert "synthetic VerSe stand-in" in html_out
    assert "not</em> from real VerSe" in html_out  # honesty note
    assert "L1" in html_out
    assert "19140" in html_out or "1.914e+04" in html_out  # mean rendered (4 sig figs)


def test_reference_section_placeholder_when_absent():
    model = asr.ReportModel(generated_at="now", reference=None)
    html_out = asr._render_reference_section(model)
    assert "Extension point" in html_out


def test_real_docs_reference_is_synthetic_verse_cohort():
    """The bundled reference artifact is currently a synthetic VerSe stand-in;
    the report must surface that honestly rather than implying real VerSe GT."""
    model = _model()
    assert model.reference is not None
    assert model.reference.is_synthetic is True
    assert model.reference.subject_count > 0


def test_corpus_legend_spells_out_failure_modes():
    """§6 references must be self-explanatory: the eight failure modes are
    spelled out in the rendered report."""
    model = _model()
    doc = asr.render_html(model)
    assert "Overlapping segments" in doc  # mode 8 description from the legend
    assert "vision.md §6" in doc  # the reference is explained, not bare
