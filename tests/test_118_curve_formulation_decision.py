"""Tests for item 118 -- decide the spinal curve formulation.

Item 118 produces **no production code**. Its two deliverables are the
decision document ``docs/spinal-curve-model.md`` and the candidate-comparison
tool ``scripts/compare_curve_candidates.py`` (loaded by path, the pattern
``tests/test_083_refresh_reference.py`` already uses -- never imported as a
package, never coupled to ``tests/``). This module is therefore the
specification of what those two artifacts must contain; neither exists yet.

Covers Acceptance Criteria AC1-AC20:

- AC1-AC5, AC7: the decision document's structure -- five ordered
  ``### `` subsections under ``## Decision``, each with non-empty
  ``**Choice:**``/``**Consequence:**``/``**Evidence:**`` lines; the deformity
  envelope marked ``PROPOSED -- pending human gate`` with no line anywhere
  claiming the gate is resolved; the ``## Measurements`` table's shape; every
  quoted Evidence number present as a table Value; the
  ``## Reproducing these numbers`` section.
- AC6: every non-VerSe measurements-table Key resolves against a freshly
  generated artifact within the document's stated tolerance; VerSe-sourced
  rows are checked only when the real cohort is reachable, else genuinely
  skipped (never a vacuous pass).
- AC8: ``progress.md``'s Human gates table already carries the row with the
  right ``Blocks`` reach -- a read-only assertion, no edit made here.
- AC9-AC17: the artifact's shape from a synthetic-only run -- candidate
  accounting, the five judgement measurements, the clean-GT sweep grid, the
  separation sweep, both circularity modes, degenerate inputs, fit
  determinism, and tool-level determinism across two ``--out`` dirs.
- AC18-AC20: cohort resolution order and the "never hard-coded" guarantee,
  layout-agnostic recursive discovery, and the objective scoliotic-case
  selection record.

**Contract details this module fixes** (the spec leaves them to the test
suite, the way item 083 fixed ``STEP_VERSE_BUILD`` etc.): the
``## Reproducing these numbers`` section carries ``**Command:**``,
``**Artifact path:**`` and ``**Tolerance:**`` bold-label lines, mirroring the
Choice/Consequence/Evidence convention already used for the five decision
sections; ``degenerate_inputs`` is keyed ``two_level``/``truncated_fov``, each
an object with boolean ``raised``/``degenerate``; ``determinism`` carries
``identical`` and ``compared_samples``; and a ``--verse-cohort`` run records
the discovered case stems under ``provenance.verse_cases`` so AC19's
layout-agnostic claim is machine-checkable.

Adversarial / edge cases:

- A synthetic Evidence number with no backing measurements-table row is
  caught by the AC5 checker (tested directly against a throwaway string, not
  only against the real document).
- A measurements-table Key that does not resolve in the fresh artifact fails
  loudly; a VerSe-sourced row is skipped-with-reason, never silently treated
  as passing.
- A cohort root that exists but holds no matching masks is a genuine skip,
  exit 0, no traceback -- distinct from a missing root.
- Nested vs. flat mask layout yield the identical discovered case list.
- The 2-level degenerate input is exercised for every evaluated candidate,
  recording booleans rather than crashing.
- ``SEGFACET_VERSE_COHORT`` env hygiene after monkeypatch teardown, as tests
  084/091 assert explicitly.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import re
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Optional

import nibabel as nib
import pytest

from segfacet.synth.clean_gt import build_clean_spine

# --------------------------------------------------------------------------- #
# Paths + module loader (mirrors tests/test_083_refresh_reference.py)
# --------------------------------------------------------------------------- #

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "compare_curve_candidates.py"
_DOC_PATH = _REPO_ROOT / "docs" / "spinal-curve-model.md"
_PROGRESS_PATH = _REPO_ROOT / "docs" / "aide" / "progress.md"

_CANDIDATE_IDS = (
    "interpolating_cubic",
    "smoothing_spline",
    "lsq_bspline_fixed_knots",
    "polynomial_per_plane",
    "robust_downweighted",
)
_JUDGEMENT_KEYS = (
    "clean_pass_through",
    "separation",
    "verse_scoliotic",
    "degenerate_inputs",
    "determinism",
)


def _load_script():
    spec = importlib.util.spec_from_file_location("compare_curve_candidates", _SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _no_traceback(text: str) -> bool:
    return "Traceback (most recent call last)" not in text


def _capture_main(mod, argv):
    out_buf, err_buf = io.StringIO(), io.StringIO()
    with redirect_stdout(out_buf), redirect_stderr(err_buf):
        rc = mod.main(argv)
    return rc, out_buf.getvalue() + err_buf.getvalue()


def _read_artifact(out: Path) -> dict:
    return json.loads((out / "curve_candidates.json").read_text(encoding="utf-8"))


def _resolve_dotted(record: dict, dotted_key: str):
    """Resolve a dot-separated path into a nested dict. Raises KeyError/TypeError
    on a broken path -- the caller decides whether that is a test failure."""
    node = record
    for segment in dotted_key.split("."):
        node = node[segment]
    return node


def real_verse_cohort_dir() -> Optional[Path]:
    """The real VerSe19 cohort root from ``SEGFACET_VERSE_COHORT`` iff the env
    var is set AND the directory exists -- the same contract
    tests/test_084_stage12_acceptance.py and
    tests/test_091_stage14_acceptance.py already use."""
    raw = os.environ.get("SEGFACET_VERSE_COHORT")
    if not raw:
        return None
    candidate = Path(raw)
    if not candidate.is_dir():
        return None
    return candidate


requires_verse = pytest.mark.skipif(
    real_verse_cohort_dir() is None,
    reason="real VerSe19 cohort not mounted (set SEGFACET_VERSE_COHORT to the VerSe19 root)",
)


def _build_standin_cohort(dest_dir: Path, n: int = 2, *, curve_amplitude_mm: float = 6.0) -> Path:
    """Write a tiny VerSe-shaped stand-in cohort of ``n`` masks named
    ``<id>_seg-vert_msk.nii.gz`` directly under ``dest_dir`` (flat layout)."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        spine = build_clean_spine(
            levels=("L1", "L2", "L3", "L4", "L5"),
            spacing=(1.0, 1.0, 1.0 + 0.1 * i),
            curve_amplitude_mm=curve_amplitude_mm,
        )
        nib.save(spine.seg_img, str(dest_dir / f"verse-standin-{i:03d}_seg-vert_msk.nii.gz"))
    return dest_dir


# =========================================================================== #
# Decision document -- parsing helpers
# =========================================================================== #

_DECISION_HEADINGS = (
    "### Family",
    "### Degrees of freedom",
    "### Parameterisation",
    "### Breaking circularity",
    "### Deformity envelope",
)


def _read_doc() -> str:
    return _DOC_PATH.read_text(encoding="utf-8")


def _decision_section(text: str) -> str:
    match = re.search(r"^## Decision\s*$", text, re.MULTILINE)
    assert match, "document has no '## Decision' section"
    rest = text[match.end() :]
    next_h2 = re.search(r"^## ", rest, re.MULTILINE)
    return rest[: next_h2.start()] if next_h2 else rest


def _subsection(decision_text: str, heading: str) -> str:
    match = re.search(rf"^{re.escape(heading)}\s*$", decision_text, re.MULTILINE)
    assert match, f"missing subsection heading {heading!r}"
    rest = decision_text[match.end() :]
    next_h3 = re.search(r"^### ", rest, re.MULTILINE)
    return rest[: next_h3.start()] if next_h3 else rest


def _labelled_line(section_text: str, label: str) -> Optional[str]:
    match = re.search(rf"^\*\*{re.escape(label)}:\*\*\s*(.+)$", section_text, re.MULTILINE)
    return match.group(1).strip() if match else None


_NUMBER_RE = re.compile(r"-?\d+\.?\d*(?:[eE][-+]?\d+)?")


def _evidence_numbers(decision_text: str) -> list:
    """Every numeric literal on an ``**Evidence:**`` line in the Decision
    section (the values AC5 requires to all be table-backed)."""
    numbers = []
    for line in decision_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("**Evidence:**"):
            numbers.extend(_NUMBER_RE.findall(stripped))
    return numbers


def _measurements_table(text: str) -> list:
    """Parse the ``## Measurements`` Markdown table into a list of row dicts."""
    match = re.search(r"^## Measurements\s*$", text, re.MULTILINE)
    assert match, "document has no '## Measurements' section"
    rest = text[match.end() :]
    next_h2 = re.search(r"^## ", rest, re.MULTILINE)
    section = rest[: next_h2.start()] if next_h2 else rest

    lines = [ln for ln in section.splitlines() if ln.strip().startswith("|")]
    assert len(lines) >= 3, "measurements table has no data rows"
    header_cells = [c.strip() for c in lines[0].strip("|").split("|")]
    rows = []
    for line in lines[2:]:  # skip header + separator
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != len(header_cells):
            continue
        rows.append(dict(zip(header_cells, cells)))
    return rows


def _reproducing_section(text: str) -> str:
    match = re.search(r"^## Reproducing these numbers\s*$", text, re.MULTILINE)
    assert match, "document has no '## Reproducing these numbers' section"
    rest = text[match.end() :]
    next_h2 = re.search(r"^## ", rest, re.MULTILINE)
    return rest[: next_h2.start()] if next_h2 else rest


def _evidence_numbers_missing_from_table(decision_text: str, table_rows: list) -> list:
    """Return the subset of Evidence-line numbers that have no backing row --
    the exact predicate AC5 requires to be empty for the real document, and
    the one directly adversarially tested against a synthetic string."""
    table_values = set()
    for row in table_rows:
        value = row.get("Value", "")
        table_values.add(value.strip())
        try:
            table_values.add(f"{float(value):g}")
        except ValueError:
            pass

    missing = []
    for number in _evidence_numbers(decision_text):
        try:
            normalised = f"{float(number):g}"
        except ValueError:
            normalised = number
        if number not in table_values and normalised not in table_values:
            missing.append(number)
    return missing


# =========================================================================== #
# AC1: five decision subsections, in order
# =========================================================================== #


def test_ac1_decision_document_has_five_sections_in_order():
    text = _read_doc()
    decision = _decision_section(text)
    found_headings = re.findall(r"^### .+$", decision, re.MULTILINE)
    assert found_headings, "no '### ' subsections found under '## Decision'"
    # The five required headings must appear, in this exact order (extra
    # headings, if any, would still leave this subsequence intact).
    positions = [found_headings.index(h) for h in _DECISION_HEADINGS if h in found_headings]
    assert len(positions) == len(_DECISION_HEADINGS), (
        f"expected headings {_DECISION_HEADINGS}, found {found_headings}"
    )
    assert positions == sorted(positions)
    assert found_headings == list(_DECISION_HEADINGS)


# =========================================================================== #
# AC2: each subsection has non-empty Choice/Consequence/Evidence lines
# =========================================================================== #


def test_ac2_each_decision_section_states_choice_consequence_evidence():
    text = _read_doc()
    decision = _decision_section(text)
    for heading in _DECISION_HEADINGS:
        section = _subsection(decision, heading)
        for label in ("Choice", "Consequence", "Evidence"):
            value = _labelled_line(section, label)
            assert value, f"{heading!r} missing non-empty **{label}:** line"


# =========================================================================== #
# AC3: deformity envelope is a gated proposal, never a settled decision
# =========================================================================== #


def test_ac3_deformity_envelope_is_proposed_pending_gate():
    text = _read_doc()
    decision = _decision_section(text)
    envelope = _subsection(decision, "### Deformity envelope")

    assert "PROPOSED — pending human gate" in envelope

    # A link to progress.md's Human gates table.
    assert re.search(r"progress\.md", envelope)
    assert re.search(r"Human gates", envelope, re.IGNORECASE)


def test_ac3_no_line_anywhere_claims_the_gate_is_settled():
    text = _read_doc()
    forbidden = ("approved", "resolved", "signed off")
    for line in text.splitlines():
        lowered = line.lower()
        if "gate" not in lowered:
            continue
        for word in forbidden:
            assert word not in lowered, f"line claims the gate is settled: {line!r}"


# =========================================================================== #
# AC4: the measurements table is well-formed
# =========================================================================== #


def test_ac4_measurements_table_well_formed():
    text = _read_doc()
    rows = _measurements_table(text)
    assert rows, "measurements table has no rows"

    header = set(rows[0].keys())
    for required in ("Key", "Value", "Units", "Source"):
        assert required in header

    for row in rows:
        for column in ("Key", "Value", "Units", "Source"):
            assert row[column], f"empty {column!r} cell in row {row!r}"
        segments = row["Key"].split(".")
        assert len(segments) >= 2, f"Key {row['Key']!r} is not a dotted path"


# =========================================================================== #
# AC5: every quoted Evidence number is a measurements-table Value
# =========================================================================== #


def test_ac5_evidence_numbers_all_appear_in_measurements_table():
    text = _read_doc()
    decision = _decision_section(text)
    rows = _measurements_table(text)
    missing = _evidence_numbers_missing_from_table(decision, rows)
    assert missing == [], f"Evidence numbers with no backing table row: {missing}"


def test_adversarial_ac5_checker_catches_an_orphan_evidence_number():
    """The AC5 predicate itself, exercised against a throwaway document that
    deliberately quotes a number no measurements row backs."""
    synthetic_decision = (
        "### Family\n"
        "**Choice:** smoothing spline\n"
        "**Consequence:** less exact fit\n"
        "**Evidence:** max pass-through 0.42 mm, unbacked outlier 99.9 mm\n"
    )
    synthetic_rows = [
        {"Key": "sweep.max_mm", "Value": "0.42", "Units": "mm", "Source": "synthetic"},
    ]
    missing = _evidence_numbers_missing_from_table(synthetic_decision, synthetic_rows)
    assert "99.9" in missing
    assert "0.42" not in missing


# =========================================================================== #
# AC7: the reproduction section states command, artifact path, tolerance
# =========================================================================== #


def test_ac7_reproducing_section_states_command_path_and_tolerance():
    text = _read_doc()
    section = _reproducing_section(text)

    command = _labelled_line(section, "Command")
    artifact_path = _labelled_line(section, "Artifact path")
    tolerance = _labelled_line(section, "Tolerance")

    assert command, "no **Command:** line"
    assert "compare_curve_candidates.py" in command
    assert artifact_path, "no **Artifact path:** line"
    assert "curve_candidates.json" in artifact_path
    assert tolerance, "no **Tolerance:** line"
    assert _NUMBER_RE.search(tolerance), "tolerance line names no number"


# =========================================================================== #
# AC6: every measurements-table Key reproduces from a fresh run
# =========================================================================== #


def _parsed_tolerance(text: str) -> float:
    section = _reproducing_section(text)
    tolerance_line = _labelled_line(section, "Tolerance")
    assert tolerance_line
    match = _NUMBER_RE.search(tolerance_line)
    assert match
    return float(match.group(0))


def _is_verse_sourced(row: dict) -> bool:
    return "verse" in row["Source"].lower()


def _assert_row_reproduces(row: dict, record: dict, tolerance: float):
    try:
        resolved = _resolve_dotted(record, row["Key"])
    except (KeyError, TypeError, IndexError) as exc:
        raise AssertionError(f"Key {row['Key']!r} does not resolve in the artifact: {exc}")
    assert resolved is not None, f"Key {row['Key']!r} resolved to None"

    try:
        expected = float(row["Value"])
        actual = float(resolved)
    except (TypeError, ValueError):
        assert str(resolved) == row["Value"], (
            f"Key {row['Key']!r}: artifact value {resolved!r} != document value {row['Value']!r}"
        )
        return
    assert abs(actual - expected) <= tolerance, (
        f"Key {row['Key']!r}: artifact {actual} vs document {expected} exceeds tolerance {tolerance}"
    )


def test_ac6_non_verse_measurements_reproduce_from_fresh_run(tmp_path):
    text = _read_doc()
    tolerance = _parsed_tolerance(text)
    rows = _measurements_table(text)
    non_verse_rows = [r for r in rows if not _is_verse_sourced(r)]
    assert non_verse_rows, "expected at least one non-VerSe measurement row"

    mod = _load_script()
    out = tmp_path / "out"
    rc = mod.main(["--out", str(out)])
    assert rc == 0
    record = _read_artifact(out)

    for row in non_verse_rows:
        _assert_row_reproduces(row, record, tolerance)


@requires_verse
def test_ac6_verse_measurements_reproduce_from_fresh_run_with_cohort(tmp_path):
    text = _read_doc()
    tolerance = _parsed_tolerance(text)
    rows = _measurements_table(text)
    verse_rows = [r for r in rows if _is_verse_sourced(r)]
    assert verse_rows, "expected at least one VerSe-sourced measurement row"

    mod = _load_script()
    out = tmp_path / "out"
    cohort = real_verse_cohort_dir()
    rc = mod.main(["--out", str(out), "--verse-cohort", str(cohort)])
    assert rc == 0
    record = _read_artifact(out)

    for row in verse_rows:
        _assert_row_reproduces(row, record, tolerance)


def test_adversarial_ac6_unresolvable_key_fails_not_silently():
    """A Key that cannot possibly resolve must raise, not be swallowed."""
    record = {"candidates": {"interpolating_cubic": {"clean_pass_through": {"max_mm": 0.1}}}}
    bad_row = {"Key": "candidates.does_not_exist.max_mm", "Value": "0.1", "Units": "mm", "Source": "synthetic"}
    with pytest.raises(AssertionError):
        _assert_row_reproduces(bad_row, record, tolerance=0.01)


# =========================================================================== #
# AC8: the human gate is already raised with the right reach (read-only)
# =========================================================================== #


def test_ac8_human_gate_row_has_correct_blocks_and_excludes_118():
    text = _PROGRESS_PATH.read_text(encoding="utf-8")
    match = re.search(r"^\|.*[Ss]pinal curve model.*\|$", text, re.MULTILINE)
    assert match, "no Human gates row mentions the spinal curve model"
    row = match.group(0)
    cells = [c.strip() for c in row.strip("|").split("|")]
    assert len(cells) >= 4, f"gate row does not look like a 4-column table row: {row!r}"
    blocks_cell = cells[1]
    for item_number in ("119", "120", "121", "123", "125"):
        assert re.search(rf"\b{item_number}\b", blocks_cell), f"Blocks cell missing {item_number}"
    assert not re.search(r"\b118\b", blocks_cell), "Blocks cell must not name item 118"


# =========================================================================== #
# AC9: the script runs standalone and writes its artifact
# =========================================================================== #


def test_ac9_script_runs_standalone_and_writes_artifact(tmp_path):
    mod = _load_script()
    assert callable(mod.main)
    out = tmp_path / "out"
    rc = mod.main(["--out", str(out)])
    assert rc == 0
    artifact_path = out / "curve_candidates.json"
    assert artifact_path.is_file()
    record = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert isinstance(record, dict)


# =========================================================================== #
# AC10: every candidate family is accounted for
# =========================================================================== #


def test_ac10_every_candidate_family_is_accounted_for(tmp_path):
    mod = _load_script()
    out = tmp_path / "out"
    mod.main(["--out", str(out)])
    record = _read_artifact(out)

    candidates = record["candidates"]
    assert candidates, "candidates block is empty"
    for candidate_id in _CANDIDATE_IDS:
        assert candidate_id in candidates, f"missing candidate {candidate_id!r}"
        entry = candidates[candidate_id]
        assert entry["status"] in {"evaluated", "excluded"}
        if entry["status"] == "excluded":
            assert entry.get("reason"), f"{candidate_id!r} excluded with no reason"


# =========================================================================== #
# AC11: every evaluated candidate carries all five judgement measurements
# =========================================================================== #


def test_ac11_evaluated_candidates_carry_all_five_measurements(tmp_path):
    mod = _load_script()
    out = tmp_path / "out"
    mod.main(["--out", str(out)])
    record = _read_artifact(out)

    evaluated = [c for c in record["candidates"].values() if c["status"] == "evaluated"]
    assert evaluated, "no candidate was evaluated"
    for entry in evaluated:
        for key in _JUDGEMENT_KEYS:
            assert key in entry, f"evaluated candidate missing {key!r}"


# =========================================================================== #
# AC12: the clean-GT sweep spans level counts and spacings
# =========================================================================== #


def test_ac12_clean_gt_sweep_spans_level_counts_and_spacings(tmp_path):
    mod = _load_script()
    out = tmp_path / "out"
    mod.main(["--out", str(out)])
    record = _read_artifact(out)

    sweep = record["sweep"]
    level_counts = sweep["level_counts"]
    spacings = sweep["spacings"]

    assert len(set(level_counts)) >= 3
    assert 2 in level_counts
    assert len(spacings) >= 3
    anisotropic = [tuple(s) for s in spacings if len(set(s)) > 1]
    assert anisotropic, "no anisotropic spacing in the sweep grid"

    for entry in record["candidates"].values():
        if entry["status"] != "evaluated":
            continue
        for mode in ("in_sample", "leave_one_out"):
            max_mm = entry["clean_pass_through"][mode]["max_mm"]
            assert isinstance(max_mm, (int, float))


# =========================================================================== #
# AC13: separation is measured at several displacement magnitudes
# =========================================================================== #


def test_ac13_separation_measured_at_several_displacement_magnitudes(tmp_path):
    mod = _load_script()
    out = tmp_path / "out"
    mod.main(["--out", str(out)])
    record = _read_artifact(out)

    for entry in record["candidates"].values():
        if entry["status"] != "evaluated":
            continue
        for mode in ("in_sample", "leave_one_out"):
            points = entry["separation"][mode]
            assert isinstance(points, list)
            magnitudes = {p["displacement_mm"] for p in points}
            assert len(magnitudes) >= 3
            for point in points:
                assert set(("clean_max_mm", "displaced_offset_mm", "margin_mm")) <= set(point.keys())
                expected_margin = point["displaced_offset_mm"] - point["clean_max_mm"]
                assert point["margin_mm"] == pytest.approx(expected_margin, abs=1e-6)


# =========================================================================== #
# AC14: both circularity modes are measured
# =========================================================================== #


def test_ac14_both_circularity_modes_present(tmp_path):
    mod = _load_script()
    out = tmp_path / "out"
    mod.main(["--out", str(out)])
    record = _read_artifact(out)

    for entry in record["candidates"].values():
        if entry["status"] != "evaluated":
            continue
        for judgement in ("clean_pass_through", "separation"):
            block = entry[judgement]
            assert "in_sample" in block
            assert "leave_one_out" in block


# =========================================================================== #
# AC15: degenerate inputs are exercised, not assumed
# =========================================================================== #


def test_ac15_degenerate_inputs_recorded_as_booleans(tmp_path):
    mod = _load_script()
    out = tmp_path / "out"
    mod.main(["--out", str(out)])
    record = _read_artifact(out)

    for entry in record["candidates"].values():
        if entry["status"] != "evaluated":
            continue
        degenerate_block = entry["degenerate_inputs"]
        for case_key in ("two_level", "truncated_fov"):
            assert case_key in degenerate_block, f"missing degenerate case {case_key!r}"
            case = degenerate_block[case_key]
            assert isinstance(case["raised"], bool)
            assert isinstance(case["degenerate"], bool)


# =========================================================================== #
# AC16: fit determinism is established by comparison
# =========================================================================== #


def test_ac16_fit_determinism_established_by_comparison(tmp_path):
    mod = _load_script()
    out = tmp_path / "out"
    mod.main(["--out", str(out)])
    record = _read_artifact(out)

    for entry in record["candidates"].values():
        if entry["status"] != "evaluated":
            continue
        determinism = entry["determinism"]
        assert isinstance(determinism["identical"], bool)
        assert isinstance(determinism["compared_samples"], int)
        assert determinism["compared_samples"] > 0
        assert determinism["identical"] is True


# =========================================================================== #
# AC17: the tool itself is deterministic across two --out dirs
# =========================================================================== #


def test_ac17_deterministic_across_two_out_dirs(tmp_path):
    mod = _load_script()
    out_a = tmp_path / "out_a"
    out_b = tmp_path / "out_b"
    mod.main(["--out", str(out_a)])
    mod.main(["--out", str(out_b)])

    record_a = _read_artifact(out_a)
    record_b = _read_artifact(out_b)

    assert record_a["candidates"] == record_b["candidates"]
    assert record_a["sweep"] == record_b["sweep"]

    # provenance is explicitly excluded from the comparison: it may legally
    # differ (timestamps, host) without affecting the compared blocks above.
    assert "provenance" in record_a
    assert "provenance" in record_b


# =========================================================================== #
# AC18: cohort path is machine-local config, never hard-coded
# =========================================================================== #


def test_ac18_no_literal_dataset_path_in_script_source():
    source = _SCRIPT_PATH.read_text(encoding="utf-8")
    assert "dataset-verse19training" not in source
    assert "import tests" not in source
    assert "from tests" not in source


def test_ac18_resolution_order_flag_then_env_then_not_found(tmp_path, monkeypatch):
    mod = _load_script()
    monkeypatch.delenv("SEGFACET_VERSE_COHORT", raising=False)

    env_cohort = _build_standin_cohort(tmp_path / "env-cohort")
    flag_cohort = _build_standin_cohort(tmp_path / "flag-cohort")

    monkeypatch.setenv("SEGFACET_VERSE_COHORT", str(env_cohort))
    try:
        # --verse-cohort wins over the env var.
        out1 = tmp_path / "out1"
        rc = mod.main(["--out", str(out1), "--verse-cohort", str(flag_cohort)])
        assert rc == 0
        record1 = _read_artifact(out1)
        discovered1 = set(record1["provenance"]["verse_cases"])
        assert discovered1, "expected cases discovered from the --verse-cohort flag"

        # No flag: falls back to the env var.
        out2 = tmp_path / "out2"
        rc = mod.main(["--out", str(out2)])
        assert rc == 0
        record2 = _read_artifact(out2)
        discovered2 = set(record2["provenance"]["verse_cases"])
        assert discovered2, "expected cases discovered from SEGFACET_VERSE_COHORT"
    finally:
        monkeypatch.delenv("SEGFACET_VERSE_COHORT", raising=False)

    # Neither flag nor env: "not found".
    out3 = tmp_path / "out3"
    rc, captured = _capture_main(mod, ["--out", str(out3)])
    assert rc == 0
    assert _no_traceback(captured)
    record3 = _read_artifact(out3)
    for entry in record3["candidates"].values():
        if entry["status"] != "evaluated":
            continue
        assert entry["verse_scoliotic"]["status"] == "skipped"
        assert entry["verse_scoliotic"]["reason"]

    assert os.environ.get("SEGFACET_VERSE_COHORT") is None


def test_ac18_missing_root_skips_verse_measurements_cleanly(tmp_path):
    mod = _load_script()
    out = tmp_path / "out"
    nonexistent = tmp_path / "no-such-verse-dir"

    rc, captured = _capture_main(mod, ["--out", str(out), "--verse-cohort", str(nonexistent)])

    assert rc == 0
    assert _no_traceback(captured)
    record = _read_artifact(out)
    for entry in record["candidates"].values():
        if entry["status"] != "evaluated":
            continue
        assert entry["verse_scoliotic"]["status"] == "skipped"
        assert entry["verse_scoliotic"]["reason"]


def test_adversarial_ac18_empty_but_present_cohort_root_skips_not_crashes(tmp_path):
    mod = _load_script()
    empty_verse_dir = tmp_path / "empty-verse"
    empty_verse_dir.mkdir()
    out = tmp_path / "out"

    rc, captured = _capture_main(mod, ["--out", str(out), "--verse-cohort", str(empty_verse_dir)])

    assert rc == 0
    assert _no_traceback(captured)
    record = _read_artifact(out)
    for entry in record["candidates"].values():
        if entry["status"] != "evaluated":
            continue
        assert entry["verse_scoliotic"]["status"] == "skipped"
        assert entry["verse_scoliotic"]["reason"]


# =========================================================================== #
# AC19: cohort discovery is layout-agnostic
# =========================================================================== #


def test_ac19_recursive_discovery_nested_vs_flat_layout_match(tmp_path):
    mod = _load_script()

    flat_root = tmp_path / "flat"
    nested_root = tmp_path / "nested"
    flat_root.mkdir()
    (nested_root / "dataset-verse19training" / "derivatives").mkdir(parents=True)

    for i in range(2):
        spine = build_clean_spine(
            levels=("L1", "L2", "L3", "L4", "L5"),
            spacing=(1.0, 1.0, 1.0 + 0.1 * i),
            curve_amplitude_mm=6.0,
        )
        name = f"verse-standin-{i:03d}_seg-vert_msk.nii.gz"
        nib.save(spine.seg_img, str(flat_root / name))
        nib.save(spine.seg_img, str(nested_root / "dataset-verse19training" / "derivatives" / name))

    out_flat = tmp_path / "out_flat"
    out_nested = tmp_path / "out_nested"
    rc_flat = mod.main(["--out", str(out_flat), "--verse-cohort", str(flat_root)])
    rc_nested = mod.main(["--out", str(out_nested), "--verse-cohort", str(nested_root)])
    assert rc_flat == 0
    assert rc_nested == 0

    cases_flat = sorted(_read_artifact(out_flat)["provenance"]["verse_cases"])
    cases_nested = sorted(_read_artifact(out_nested)["provenance"]["verse_cases"])
    assert cases_flat, "expected at least one case discovered from the flat layout"
    assert cases_flat == cases_nested


# =========================================================================== #
# AC20: scoliotic-case selection is objective and recorded
# =========================================================================== #


def test_ac20_scoliotic_ranking_and_selection_rule_recorded(tmp_path):
    mod = _load_script()
    cohort = _build_standin_cohort(tmp_path / "cohort", n=3, curve_amplitude_mm=20.0)
    out = tmp_path / "out"
    rc = mod.main(["--out", str(out), "--verse-cohort", str(cohort)])
    assert rc == 0
    record = _read_artifact(out)

    for entry in record["candidates"].values():
        if entry["status"] != "evaluated":
            continue
        scoliotic = entry["verse_scoliotic"]
        assert scoliotic["status"] in {"measured", "skipped"}
        if scoliotic["status"] != "measured":
            continue
        ranked = scoliotic["ranked"]
        assert ranked, "expected a non-empty ranking for a non-empty cohort"
        deviations = [r["coronal_deviation_mm"] for r in ranked]
        assert deviations == sorted(deviations, reverse=True)
        assert scoliotic["selection_rule"]


def test_ac20_no_qualifying_case_records_a_finding_not_an_omission(tmp_path):
    mod = _load_script()
    # Deliberately straight (curve_amplitude_mm=0) stand-in spines: no case
    # should exceed any plausible curvature threshold.
    cohort = _build_standin_cohort(tmp_path / "cohort", n=2, curve_amplitude_mm=0.0)
    out = tmp_path / "out"
    rc = mod.main(["--out", str(out), "--verse-cohort", str(cohort)])
    assert rc == 0
    record = _read_artifact(out)

    for entry in record["candidates"].values():
        if entry["status"] != "evaluated":
            continue
        scoliotic = entry["verse_scoliotic"]
        if scoliotic["status"] != "measured":
            continue
        if scoliotic["selected"] == []:
            assert scoliotic.get("finding"), "empty selection with no recorded finding"


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adversarial_out_dir_under_not_yet_existing_parent(tmp_path):
    mod = _load_script()
    out = tmp_path / "brand_new_parent" / "nested" / "out"
    assert not out.parent.exists()

    rc = mod.main(["--out", str(out)])

    assert rc == 0
    assert out.is_dir()
    assert (out / "curve_candidates.json").is_file()


def test_adversarial_rerun_into_same_out_overwrites_cleanly(tmp_path):
    mod = _load_script()
    out = tmp_path / "out"
    mod.main(["--out", str(out)])
    record_1 = _read_artifact(out)

    rc2 = mod.main(["--out", str(out)])
    record_2 = _read_artifact(out)

    assert rc2 == 0
    assert record_1["candidates"] == record_2["candidates"]
    assert record_1["sweep"] == record_2["sweep"]


def test_adversarial_two_level_degenerate_case_never_raises(tmp_path):
    mod = _load_script()
    out = tmp_path / "out"
    mod.main(["--out", str(out)])
    record = _read_artifact(out)

    for candidate_id, entry in record["candidates"].items():
        if entry["status"] != "evaluated":
            continue
        two_level = entry["degenerate_inputs"]["two_level"]
        assert two_level["raised"] is False, f"{candidate_id} raised on a 2-level input"


def test_adversarial_single_label_and_two_label_verse_masks_never_crash(tmp_path):
    mod = _load_script()
    cohort_dir = tmp_path / "mixed-cohort"
    cohort_dir.mkdir()

    spine_one = build_clean_spine(levels=("L3",), spacing=(1.0, 1.0, 1.0), curve_amplitude_mm=0.0)
    nib.save(spine_one.seg_img, str(cohort_dir / "one-label_seg-vert_msk.nii.gz"))

    spine_two = build_clean_spine(levels=("L3", "L4"), spacing=(1.0, 1.0, 1.0), curve_amplitude_mm=0.0)
    nib.save(spine_two.seg_img, str(cohort_dir / "two-label_seg-vert_msk.nii.gz"))

    rc, captured = _capture_main(mod, ["--out", str(tmp_path / "out"), "--verse-cohort", str(cohort_dir)])
    assert rc == 0
    assert _no_traceback(captured)


def test_adversarial_env_hygiene_after_monkeypatch(tmp_path, monkeypatch):
    mod = _load_script()
    assert os.environ.get("SEGFACET_VERSE_COHORT") is None
    monkeypatch.setenv("SEGFACET_VERSE_COHORT", str(tmp_path / "some-cohort"))
    mod.main(["--out", str(tmp_path / "out")])
    monkeypatch.delenv("SEGFACET_VERSE_COHORT", raising=False)
    assert os.environ.get("SEGFACET_VERSE_COHORT") is None
