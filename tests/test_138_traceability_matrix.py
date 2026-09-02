"""Tests for item 138 -- the generated failure-mode <-> rule <-> feature
traceability matrix (``segfacet.traceability`` and its two committed
artifacts, ``docs/aide/traceability_matrix.generated.{json,md}``).

Covers Acceptance Criteria AC1-AC33 (AC12/AC15 parametrised over the eight
§6 modes, AC18/AC23 over the ten registered rules), plus adversarial
coverage for the three fail-loudly directions (AC25-AC27), a stale rung, a
stale mechanism, a re-narrowed ``reference_delta`` declaration (AC32), a
mode-to-rule hole, and edge cases for a singleton-rule mode and a
zero-feature rule.

This module reads the corrected spec (docs/aide/items/138-...md, including
its "Correction (2026-09-02, before implementation)" Decisions entry):
``reference_delta`` declares modes ``(1, 2)``, mode 1's rule list therefore
contains both ``mislabel`` and ``reference_delta``, and the analytic edge set
is three edges over two rules -- ``(1, reference_delta)``, ``(2, bounds)``,
``(2, reference_delta)`` -- not the pre-correction two-edge shape.

AC31 -- no character-count threshold. Item 137's own defect (recorded in
``docs/aide/insights.md``, 2026-09-02) was a mechanism sentence held to a
character floor rather than to its content. This module checks every
mechanism/rung/qualifier string against live state instead -- an anchor
path, a corpus ``case_id``, or a listed ``rule_id``, each re-derived here --
and a dedicated test (``test_ac31_no_character_count_threshold_assertions``)
inspects this module's own source to confirm no such floor crept back in.

Field-name note: the item spec pins the JSON's *content* precisely (per-AC)
but leaves several container shapes unstated (e.g. whether ``modes``/
``rules`` are JSON objects keyed by mode/rule-id, or lists of records). This
module's ``_mode_records``/``_rule_records`` helpers accept either shape;
the field *names* it reads (``rung``, ``mechanism``, ``rules``,
``rule_attribution``, ``pipeline_detected``, ``cases``, ``anchor_paths``,
``feature_paths``, ``granularity``, ``modes``, ``declaration_state``,
``mode_less_reason``, ``feature_paths_qualifier``) are this test module's own
executable statement of the contract, derived from the spec's prose and
Implementation Steps.
"""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]

RUNGS = ("synthetic-demonstrable", "needs-real-data", "structurally-unobservable")
MODES = tuple(range(1, 9))
RULE_IDS = (
    "border",
    "bounds",
    "coverage",
    "fragmentation",
    "intensity",
    "intensity_reference_delta",
    "mislabel",
    "overlap",
    "reference_delta",
    "sequence",
)

_COMMITTED_JSON = _REPO_ROOT / "docs" / "aide" / "traceability_matrix.generated.json"
_COMMITTED_MD = _REPO_ROOT / "docs" / "aide" / "traceability_matrix.generated.md"


# =========================================================================== #
# House fixtures / helpers
# =========================================================================== #


@pytest.fixture
def isolated_registry():
    """Snapshot/restore the rule registry (house pattern from
    ``tests/test_026_rule_engine_core.py`` / ``test_136`` / ``test_137``), so
    a stub rule registered for an adversarial case cannot leak into another
    test."""
    from segfacet.heuristics.rule import _RULES

    snapshot = dict(_RULES)
    yield
    _RULES.clear()
    _RULES.update(snapshot)


def _mode_records(payload: dict) -> dict:
    """Normalise the JSON's ``modes`` direction to ``{mode_int: record}``,
    accepting either a dict keyed by mode (string or int) or a list of
    records each carrying a ``mode`` field."""
    modes = payload["modes"]
    if isinstance(modes, dict):
        return {int(k): v for k, v in modes.items()}
    return {int(r["mode"]): r for r in modes}


def _rule_records(payload: dict) -> dict:
    """Normalise the JSON's ``rules`` direction to ``{rule_id: record}``."""
    rules = payload["rules"]
    if isinstance(rules, dict):
        return dict(rules)
    return {r["rule_id"]: r for r in rules}


def _mode_record(payload: dict, mode: int) -> dict:
    records = _mode_records(payload)
    assert mode in records, (mode, sorted(records))
    return records[mode]


def _manifest_cases() -> list:
    payload = json.loads((_REPO_ROOT / "tests" / "corpus" / "manifest.json").read_text(encoding="utf-8"))
    cases = payload["cases"]
    assert cases, "expected a non-empty corpus manifest"
    return cases


def _manifest_detection_by_case_id() -> dict:
    return {c["case_id"]: c.get("detection") for c in _manifest_cases()}


def _vision_mode_titles() -> dict:
    text = (_REPO_ROOT / "docs" / "aide" / "vision.md").read_text(encoding="utf-8")
    section_match = re.search(
        r"^## 6\. Segmentation Failure Modes[^\n]*\n(.*?)(?=^## \d|\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert section_match is not None, "expected a '## 6. Segmentation Failure Modes' section"
    section_text = section_match.group(1)
    items = re.findall(r"^\d+\.\s+(.+)$", section_text, flags=re.MULTILINE)
    assert items, "expected numbered §6 items"
    titles = {}
    for index, raw in enumerate(items, start=1):
        title = raw.strip()
        if title.endswith("."):
            title = title[:-1]
        title = re.sub(r"\s+", " ", title).strip()
        titles[index] = title
    return titles


def _token_in_mechanism(token: str, mechanism: str) -> bool:
    """Whole-token containment: ``token`` must appear in ``mechanism`` at a
    word boundary on both sides, so a one-character-off near-miss (e.g.
    ``mode8_force_overlaps`` for the real ``mode8_force_overlap``) does not
    count as a match."""
    return re.search(r"\b" + re.escape(token) + r"\b", mechanism) is not None


def _md_lines() -> list:
    text = _COMMITTED_MD.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines, "expected a non-empty committed markdown file"
    return lines


def _row_for_mode(lines: list, mode: int):
    for line in lines:
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells and cells[0] == str(mode):
            return line
    return None


def _row_for_rule(lines: list, rule_id: str):
    for line in lines:
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells and cells[0] == rule_id:
            return line
    return None


def _patch_mode_rungs(monkeypatch, traceability_module, mode: int, **replacements):
    """Replace ``traceability_module.MODE_RUNGS[mode]`` with a
    ``dataclasses.replace`` of its current value, via ``monkeypatch.setattr``
    on the whole module attribute (never a container mutation) so this
    works whether ``MODE_RUNGS`` is a plain dict or an immutable mapping."""
    original_map = traceability_module.MODE_RUNGS
    original_entry = original_map[mode]
    patched_map = dict(original_map)
    patched_map[mode] = dataclasses.replace(original_entry, **replacements)
    monkeypatch.setattr(traceability_module, "MODE_RUNGS", patched_map)


# =========================================================================== #
# AC1: stable public surface
# =========================================================================== #


def test_ac1_public_surface_and_zero_argument_build_matrix():
    import segfacet.traceability as traceability

    for name in ("build_matrix", "matrix_to_dict", "render_markdown", "main"):
        assert hasattr(traceability, name), name
        assert name in traceability.__all__, name
        assert callable(getattr(traceability, name)), name

    matrix = traceability.build_matrix()
    assert matrix is not None


# =========================================================================== #
# AC2: zero-argument regeneration, and redirectable
# =========================================================================== #


def test_ac2_main_redirects_writes_and_leaves_committed_artifacts_unchanged(tmp_path):
    import segfacet.traceability as traceability

    before_json = _COMMITTED_JSON.read_bytes()
    before_md = _COMMITTED_MD.read_bytes()
    assert before_json, "expected a non-empty committed JSON artifact"
    assert before_md, "expected a non-empty committed markdown artifact"

    json_dest = tmp_path / "out.json"
    md_dest = tmp_path / "out.md"
    traceability.main(["--json", str(json_dest), "--md", str(md_dest)])

    assert json_dest.exists()
    assert md_dest.exists()

    after_json = _COMMITTED_JSON.read_bytes()
    after_md = _COMMITTED_MD.read_bytes()
    assert after_json == before_json
    assert after_md == before_md


def test_ac2_default_output_paths_are_the_committed_docs_aide_paths(monkeypatch):
    import segfacet.traceability as traceability

    calls = []

    def _fake_write_bytes(self, data):
        calls.append(self)
        return len(data)

    monkeypatch.setattr(Path, "write_bytes", _fake_write_bytes)
    traceability.main([])

    assert calls, "expected main() with no args to attempt at least one write"
    written = {p.as_posix() for p in calls}
    assert any(p.endswith("docs/aide/traceability_matrix.generated.json") for p in written), written
    assert any(p.endswith("docs/aide/traceability_matrix.generated.md") for p in written), written


# =========================================================================== #
# AC3: byte-reproducible run-to-run
# =========================================================================== #


def test_ac3_artifacts_are_byte_reproducible_run_to_run(tmp_path):
    import segfacet.traceability as traceability

    json_a, md_a = tmp_path / "a.json", tmp_path / "a.md"
    json_b, md_b = tmp_path / "b.json", tmp_path / "b.md"

    traceability.main(["--json", str(json_a), "--md", str(md_a)])
    traceability.main(["--json", str(json_b), "--md", str(md_b)])

    bytes_a_json, bytes_b_json = json_a.read_bytes(), json_b.read_bytes()
    bytes_a_md, bytes_b_md = md_a.read_bytes(), md_b.read_bytes()
    assert bytes_a_json, "expected non-empty JSON output"
    assert bytes_a_md, "expected non-empty markdown output"

    assert bytes_a_json == bytes_b_json
    assert bytes_a_md == bytes_b_md


# =========================================================================== #
# AC4: the committed JSON is a fresh build (parsed comparison, A7)
# =========================================================================== #


def test_ac4_committed_json_parses_to_a_fresh_build():
    import segfacet.traceability as traceability

    committed_text = _COMMITTED_JSON.read_text(encoding="utf-8")
    committed_payload = json.loads(committed_text)
    assert committed_payload, "expected a non-empty committed JSON payload"

    fresh_payload = traceability.matrix_to_dict(traceability.build_matrix())
    normalised_fresh = json.loads(json.dumps(fresh_payload, sort_keys=True))
    assert normalised_fresh == committed_payload


# =========================================================================== #
# AC5: the committed Markdown agrees with the committed JSON
# =========================================================================== #


def test_ac5_markdown_rows_agree_with_json_for_every_mode_and_rule():
    committed_payload = json.loads(_COMMITTED_JSON.read_text(encoding="utf-8"))
    lines = _md_lines()

    modes = _mode_records(committed_payload)
    assert modes, "expected at least one mode record in committed JSON"
    for mode, record in modes.items():
        row = _row_for_mode(lines, mode)
        assert row is not None, mode
        assert record["rules"], mode
        for rule_id in record["rules"]:
            assert rule_id in row, (mode, rule_id)
        assert record["rung"] in row, mode

    rules = _rule_records(committed_payload)
    assert rules, "expected at least one rule record in committed JSON"
    for rule_id, record in rules.items():
        row = _row_for_rule(lines, rule_id)
        assert row is not None, rule_id
        for mode in record["modes"]:
            assert str(mode) in row, (rule_id, mode)
        assert record["declaration_state"] in row, rule_id


# =========================================================================== #
# AC6: LF bytes, one trailing newline
# =========================================================================== #


def test_ac6_both_artifacts_are_lf_bytes_with_one_trailing_newline():
    for path in (_COMMITTED_JSON, _COMMITTED_MD):
        data = path.read_bytes()
        assert data, path
        assert b"\r" not in data, path
        assert data.endswith(b"\n"), path
        assert not data.endswith(b"\n\n"), path


# =========================================================================== #
# AC7: .gitattributes pins both new paths eol=lf
# =========================================================================== #


def test_ac7_gitattributes_pins_both_new_paths_eol_lf():
    text = (_REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")
    for rel_path in (
        "docs/aide/traceability_matrix.generated.json",
        "docs/aide/traceability_matrix.generated.md",
    ):
        pattern = re.compile(re.escape(rel_path) + r"[^\n]*eol=lf")
        assert pattern.search(text), rel_path


# =========================================================================== #
# AC8: the mode set is §6's, taken from code
# =========================================================================== #


def test_ac8_mode_set_equals_mode_anchor_paths_keys():
    import segfacet.feature_docs as feature_docs_module
    import segfacet.traceability as traceability

    d = traceability.matrix_to_dict(traceability.build_matrix())
    modes = _mode_records(d)
    assert modes, "expected at least one mode record"
    assert set(modes.keys()) == set(feature_docs_module.MODE_ANCHOR_PATHS.keys())


# =========================================================================== #
# AC9: mode titles transcribed from vision.md §6
# =========================================================================== #

# Hand-transcribed from docs/aide/vision.md §6 "Segmentation Failure Modes"
# (lines 279-286 as of this writing), independently of
# ``_vision_mode_titles()`` / ``traceability._vision_mode_titles()`` -- both
# of those parse §6 with the identical regex, so comparing the builder's
# output only to that helper's output would let a shared parsing bug through
# undetected (both sides would agree with each other while disagreeing with
# the actual document). These literals are the trailing-period-stripped,
# whitespace-normalised title text exactly as §6 states it, preserving its
# em dashes and arrows. If §6's wording changes, these must be updated by
# hand to match -- there is no automated way to keep them in sync.
VISION_SECTION_SIX_MODE_TITLES = {
    1: "Label not aligned with the anatomical vertebra it names",
    2: "Over-/under-segmentation — fused or fragmented vertebra segments",
    3: "Disconnected components / islands, especially tiny rogue segments",
    4: "Semantic mislabelling (wrong vertebra identification)",
    5: "Not all vertebrae in the image are segmented",
    6: "Partial vertebra at the image border whose appearance changes",
    7: "Non-continuous label sequence (e.g. L1 → T12 → L2 → L5)",
    8: "Overlapping segments",
}


def test_ac9_mode_titles_match_the_hand_transcribed_vision_literals():
    """Independent ground truth: compares the built titles directly against
    literals transcribed by hand from vision.md §6, not against another
    parse of the same section -- this is the assertion that can actually
    catch a parser bug shared by the builder and this test module."""
    import segfacet.traceability as traceability

    d = traceability.matrix_to_dict(traceability.build_matrix())
    modes = _mode_records(d)
    assert modes
    assert set(modes.keys()) == set(VISION_SECTION_SIX_MODE_TITLES.keys())
    for mode, record in modes.items():
        assert record["title"] == VISION_SECTION_SIX_MODE_TITLES[mode], mode


def test_ac9_mode_titles_are_transcribed_from_vision_section_six():
    """Complementary derived check: still useful as a live-document guard
    (it fails loudly if §6 is edited and the hand-transcribed literals above
    are not updated to match), but it is not the AC9 ground-truth check --
    see test_ac9_mode_titles_match_the_hand_transcribed_vision_literals."""
    import segfacet.traceability as traceability

    d = traceability.matrix_to_dict(traceability.build_matrix())
    modes = _mode_records(d)
    vision_titles = _vision_mode_titles()
    assert modes and vision_titles
    for mode, record in modes.items():
        assert record["title"] == vision_titles[mode], mode


# =========================================================================== #
# AC10: mode -> rule is complete and reported complete
# =========================================================================== #


def test_ac10_mode_to_rule_direction_complete_and_every_mode_has_a_rule():
    import segfacet.traceability as traceability

    d = traceability.matrix_to_dict(traceability.build_matrix())
    modes = _mode_records(d)
    assert modes
    for mode, record in modes.items():
        assert record["rules"], mode

    direction = d["directions"]["mode_to_rule"]
    assert direction["complete"] is True
    assert direction["holes"] == []


# =========================================================================== #
# AC11: mode rule lists derived from the shipped declarations
# =========================================================================== #


def test_ac11_mode_rule_lists_are_derived_from_shipped_declarations():
    from segfacet.heuristics.rule import iter_rules
    import segfacet.traceability as traceability

    expected_by_mode: dict = {}
    for rule in iter_rules():
        decl = rule.mode_declaration
        if decl is None:
            continue
        for mode in decl.modes:
            expected_by_mode.setdefault(mode, set()).add(rule.rule_id)
    assert expected_by_mode, "expected at least one rule to declare at least one mode"

    d = traceability.matrix_to_dict(traceability.build_matrix())
    modes = _mode_records(d)
    for mode, record in modes.items():
        expected = sorted(expected_by_mode.get(mode, set()))
        assert record["rules"] == expected, mode


# =========================================================================== #
# AC12: every mode row carries a rung from the closed vocabulary
# =========================================================================== #


@pytest.mark.parametrize("mode", MODES)
def test_ac12_mode_rung_is_member_of_closed_vocabulary(mode):
    import segfacet.traceability as traceability

    d = traceability.matrix_to_dict(traceability.build_matrix())
    record = _mode_record(d, mode)
    assert record["rung"] in RUNGS, record["rung"]


def test_adv_ac12_stale_rung_outside_vocabulary_is_detectable(monkeypatch):
    import segfacet.traceability as traceability

    _patch_mode_rungs(monkeypatch, traceability, 8, rung="not-a-real-rung")

    d = traceability.matrix_to_dict(traceability.build_matrix())
    record = _mode_record(d, 8)
    assert record["rung"] not in RUNGS, record["rung"]


# =========================================================================== #
# AC13: mode 8's rung names the single-channel mechanism
# =========================================================================== #


def test_ac13_mode8_rung_and_mechanism_name_the_single_channel_mechanism():
    import segfacet.traceability as traceability

    d = traceability.matrix_to_dict(traceability.build_matrix())
    mode8 = _mode_record(d, 8)
    assert mode8["rung"] == "structurally-unobservable"
    assert "single-channel" in mode8["mechanism"]
    assert "label map" in mode8["mechanism"]


# =========================================================================== #
# AC14: mode 8 is not pipeline-detected, from the manifest
# =========================================================================== #


def test_ac14_mode8_not_pipeline_detected_names_reconstructed_case():
    import segfacet.traceability as traceability

    manifest_detection = _manifest_detection_by_case_id()
    assert "mode8_force_overlap" in manifest_detection

    d = traceability.matrix_to_dict(traceability.build_matrix())
    mode8 = _mode_record(d, 8)
    assert mode8["pipeline_detected"] is False

    cases = mode8["cases"]
    assert cases, "expected mode 8 to name at least one corpus case"
    case_ids = {c["case_id"] for c in cases}
    assert "mode8_force_overlap" in case_ids
    named = next(c for c in cases if c["case_id"] == "mode8_force_overlap")
    assert named["detection"] == manifest_detection["mode8_force_overlap"]
    assert named["detection"] == "reconstructed_record"


# =========================================================================== #
# AC15: rung and corpus detection are cross-checked
# =========================================================================== #


@pytest.mark.parametrize("mode", MODES)
def test_ac15_rung_and_pipeline_detected_cross_check(mode):
    import segfacet.traceability as traceability

    d = traceability.matrix_to_dict(traceability.build_matrix())
    record = _mode_record(d, mode)
    if record["rung"] == "synthetic-demonstrable":
        assert record["pipeline_detected"] is True, mode
    elif record["rung"] == "structurally-unobservable":
        assert record["pipeline_detected"] is False, mode


def test_adv_ac15_cross_check_violation_when_mode8_rung_monkeypatched_synthetic(monkeypatch):
    import segfacet.traceability as traceability

    _patch_mode_rungs(monkeypatch, traceability, 8, rung="synthetic-demonstrable")

    d = traceability.matrix_to_dict(traceability.build_matrix())
    mode8 = _mode_record(d, 8)
    # AC15 requires pipeline_detected True whenever rung is
    # synthetic-demonstrable; mode 8 is still (correctly) reconstructed, so
    # the two facts below jointly demonstrate the cross-check now fails.
    assert mode8["rung"] == "synthetic-demonstrable"
    assert mode8["pipeline_detected"] is False


# =========================================================================== #
# AC16: modes 1 and 4 are recorded synthetic-demonstrable
# =========================================================================== #


@pytest.mark.parametrize("mode, case_id", [(1, "mode1_displace"), (4, "mode4_relabel_swap")])
def test_ac16_modes_one_and_four_are_synthetic_demonstrable(mode, case_id):
    import segfacet.traceability as traceability

    manifest_detection = _manifest_detection_by_case_id()
    assert case_id in manifest_detection

    d = traceability.matrix_to_dict(traceability.build_matrix())
    record = _mode_record(d, mode)
    assert record["rung"] == "synthetic-demonstrable"
    assert record["pipeline_detected"] is True

    cases = record["cases"]
    assert cases, mode
    case_ids = {c["case_id"] for c in cases}
    assert case_id in case_ids
    named = next(c for c in cases if c["case_id"] == case_id)
    assert named["detection"] == manifest_detection[case_id]
    assert named["detection"] == "pipeline"


def test_adv_ac16_mode1_rung_unmoved_by_reference_delta_joining_its_rule_list():
    """A rung is a property of the mode, independent of how many rules
    declare it -- mode 1 gaining reference_delta (b1c593c) must not move
    it."""
    import segfacet.traceability as traceability

    d = traceability.matrix_to_dict(traceability.build_matrix())
    mode1 = _mode_record(d, 1)
    assert "reference_delta" in mode1["rules"], mode1["rules"]
    assert "mislabel" in mode1["rules"], mode1["rules"]
    assert mode1["rung"] == "synthetic-demonstrable"
    assert mode1["pipeline_detected"] is True


# =========================================================================== #
# AC17: mode 7's rung records its own cap
# =========================================================================== #


def test_ac17_mode7_rung_records_its_own_cap():
    import segfacet.traceability as traceability

    d = traceability.matrix_to_dict(traceability.build_matrix())
    mode7 = _mode_record(d, 7)
    assert mode7["rung"] == "needs-real-data"
    assert "rank(v) == v - 1" in mode7["mechanism"]
    assert "L1 → T12 → L2 → L5" in mode7["mechanism"]


# =========================================================================== #
# AC18: rule -> mode is complete and reported complete
# =========================================================================== #


def test_ac18_rule_to_mode_direction_complete_with_one_record_per_rule():
    from segfacet.heuristics.rule import iter_rules
    import segfacet.traceability as traceability

    rule_ids = {r.rule_id for r in iter_rules()}
    assert rule_ids

    d = traceability.matrix_to_dict(traceability.build_matrix())
    rules = _rule_records(d)
    assert set(rules.keys()) == rule_ids

    direction = d["directions"]["rule_to_mode"]
    assert direction["complete"] is True
    assert direction["holes"] == []


@pytest.mark.parametrize("rule_id", RULE_IDS)
def test_ac18_rule_record_carries_modes_xor_mode_less_reason(rule_id):
    import segfacet.traceability as traceability

    d = traceability.matrix_to_dict(traceability.build_matrix())
    record = _rule_records(d)[rule_id]
    has_modes = bool(record["modes"])
    has_reason = bool(record.get("mode_less_reason"))
    assert has_modes != has_reason, (rule_id, record)


# =========================================================================== #
# AC19: every mode -> rule edge is attributed corpus or analytic, from the
# corpus map
# =========================================================================== #


def test_ac19_every_mode_to_rule_edge_is_attributed_from_the_corpus_map():
    import segfacet.catalogue as catalogue_module
    import segfacet.traceability as traceability

    corpus_map = catalogue_module.scan_synth_rule_mode_map()
    d = traceability.matrix_to_dict(traceability.build_matrix())
    modes = _mode_records(d)
    assert modes

    checked = False
    for mode, record in modes.items():
        attribution = record["rule_attribution"]
        assert attribution, mode
        for rule_id, tag in attribution.items():
            checked = True
            assert tag in ("corpus", "analytic"), (mode, rule_id, tag)
            expected = "corpus" if mode in corpus_map.get(rule_id, ()) else "analytic"
            assert tag == expected, (mode, rule_id, tag, expected)
    assert checked, "expected at least one mode-to-rule edge"


# =========================================================================== #
# AC20: the analytic edges are exactly the edges of rules the corpus map
# never designates
# =========================================================================== #


def test_ac20_analytic_edges_equal_edges_of_rules_the_corpus_map_never_designates():
    from segfacet.heuristics.rule import iter_rules
    import segfacet.catalogue as catalogue_module
    import segfacet.traceability as traceability

    corpus_map = catalogue_module.scan_synth_rule_mode_map()
    expected_analytic = set()
    for rule in iter_rules():
        decl = rule.mode_declaration
        if decl is None or rule.rule_id in corpus_map:
            continue
        for mode in decl.modes:
            expected_analytic.add((mode, rule.rule_id))

    d = traceability.matrix_to_dict(traceability.build_matrix())
    modes = _mode_records(d)
    actual_all_edges = set()
    actual_analytic = set()
    for mode, record in modes.items():
        for rule_id, tag in record["rule_attribution"].items():
            actual_all_edges.add((mode, rule_id))
            if tag == "analytic":
                actual_analytic.add((mode, rule_id))

    assert actual_all_edges, "expected at least one mode-to-rule edge"
    assert actual_analytic == expected_analytic

    witness = {(1, "reference_delta"), (2, "bounds"), (2, "reference_delta")}
    assert actual_analytic == witness
    assert len(actual_all_edges) == 11
    assert len(actual_all_edges - actual_analytic) == 8

    by_rule: dict = {}
    for mode, rule_id in actual_analytic:
        by_rule.setdefault(rule_id, set()).add("analytic")
    for mode, rule_id in actual_all_edges - actual_analytic:
        by_rule.setdefault(rule_id, set()).add("corpus")
    for rule_id, tags in by_rule.items():
        assert len(tags) == 1, (rule_id, tags)


def test_adv_ac20_mistagged_corpus_evidence_changes_no_attribution(monkeypatch):
    """A6: attribution is derived from the corpus map, never from the
    declaration's own free-form evidence tag -- retagging bounds' evidence
    as ('corpus',) leaves the (2, bounds) edge attributed 'analytic'."""
    from segfacet.heuristics.rule import _RULES
    import segfacet.heuristics.rule as rule_mod
    import segfacet.traceability as traceability

    rule = _RULES["bounds"]
    replacement = rule_mod.RuleModeDeclaration(modes=(2,), evidence=("corpus",))
    monkeypatch.setattr(rule, "mode_declaration", replacement)

    d = traceability.matrix_to_dict(traceability.build_matrix())
    mode2 = _mode_record(d, 2)
    assert "bounds" in mode2["rule_attribution"], mode2["rule_attribution"]
    assert mode2["rule_attribution"]["bounds"] == "analytic"


# =========================================================================== #
# AC21: the feature direction reports its counts against the live catalogue
# =========================================================================== #


def test_ac21_feature_direction_counts_match_a_fresh_catalogue():
    import segfacet.catalogue as catalogue_module
    import segfacet.traceability as traceability

    cat = catalogue_module.build_catalogue(strict=True)
    assert cat.entries, "expected a non-empty catalogue"

    total = len(cat.entries)
    read_by_rule = sum(1 for e in cat.entries if e.consuming_rules)
    read_by_no_rule = total - read_by_rule
    unwired = sum(1 for e in cat.entries if e.status == "unwired")

    d = traceability.matrix_to_dict(traceability.build_matrix())
    features = d["features"]
    assert features["total_paths"] == total
    assert features["read_by_rule"] == read_by_rule
    assert features["read_by_no_rule"]["count"] == read_by_no_rule
    assert features["unwired"] == unwired


# =========================================================================== #
# AC22: the "inventory, not a gap" qualifier sits with the count
# =========================================================================== #


def test_ac22_inventory_not_a_gap_qualifier_sits_with_the_count():
    import segfacet.traceability as traceability

    d = traceability.matrix_to_dict(traceability.build_matrix())
    read_by_no_rule = d["features"]["read_by_no_rule"]
    assert isinstance(read_by_no_rule, dict)
    assert "count" in read_by_no_rule
    assert read_by_no_rule["required"] is False
    qualifier = read_by_no_rule["qualifier"]
    assert "inventory" in qualifier
    assert "not a gap" in qualifier


def test_ac22_committed_markdown_prints_qualifier_beside_the_count():
    md_text = _COMMITTED_MD.read_text(encoding="utf-8")
    committed_payload = json.loads(_COMMITTED_JSON.read_text(encoding="utf-8"))

    idx = md_text.find("inventory")
    assert idx != -1, "expected the inventory qualifier in the committed markdown"
    window = md_text[max(0, idx - 400) : idx + 400]

    count = committed_payload["features"]["read_by_no_rule"]["count"]
    assert str(count) in window, (count, window)


# =========================================================================== #
# AC23: per-rule feature sets derived from the catalogue
# =========================================================================== #


@pytest.mark.parametrize("rule_id", RULE_IDS)
def test_ac23_rule_feature_paths_are_derived_from_the_catalogue(rule_id):
    import segfacet.catalogue as catalogue_module
    import segfacet.traceability as traceability

    cat = catalogue_module.build_catalogue(strict=True)
    assert cat.entries

    expected = sorted(e.path for e in cat.entries if rule_id in e.consuming_rules)

    d = traceability.matrix_to_dict(traceability.build_matrix())
    record = _rule_records(d)[rule_id]
    assert record["feature_paths"] == expected, rule_id


# =========================================================================== #
# AC24: per-mode feature sets are the union of the mode's rules' paths plus
# its anchors
# =========================================================================== #


@pytest.mark.parametrize("mode", MODES)
def test_ac24_mode_feature_paths_are_the_union_of_rule_paths_plus_anchors(mode):
    import segfacet.feature_docs as feature_docs_module
    import segfacet.traceability as traceability

    d = traceability.matrix_to_dict(traceability.build_matrix())
    modes = _mode_records(d)
    rules = _rule_records(d)
    record = modes[mode]
    assert record["rules"], mode

    expected = set(feature_docs_module.MODE_ANCHOR_PATHS[mode])
    for rule_id in record["rules"]:
        expected |= set(rules[rule_id]["feature_paths"])

    assert record["feature_paths"] == sorted(expected), mode


# =========================================================================== #
# AC25: a corpus-designated rule id that no rule registers is reported
# =========================================================================== #


def test_ac25_no_unregistered_designated_rule_id_on_this_tree():
    import segfacet.traceability as traceability

    d = traceability.matrix_to_dict(traceability.build_matrix())
    assert d["corpus_designated_unregistered_rule_ids"] == []


def test_ac25_unregistered_designated_rule_id_is_reported_and_fails_completeness(monkeypatch):
    import segfacet.catalogue as catalogue_module
    import segfacet.traceability as traceability

    real_map = catalogue_module.scan_synth_rule_mode_map()

    def _patched():
        mapping = dict(real_map)
        mapping["boundary"] = (6,)
        return mapping

    monkeypatch.setattr(catalogue_module, "scan_synth_rule_mode_map", _patched)

    d = traceability.matrix_to_dict(traceability.build_matrix())
    assert "boundary" in d["corpus_designated_unregistered_rule_ids"]
    assert d["directions"]["mode_to_rule"]["complete"] is False


def test_adv_mode_to_rule_hole_when_a_declaration_is_monkeypatched_mode_less(monkeypatch):
    """Adversarial -- mode -> rule hole. Monkeypatching the live declaration
    of ``overlap`` to a mode-less one makes mode 8 a hole naming the mode,
    with complete: false."""
    from segfacet.heuristics.rule import _RULES
    import segfacet.heuristics.rule as rule_mod
    import segfacet.traceability as traceability

    rule = _RULES["overlap"]
    replacement = rule_mod.RuleModeDeclaration(
        mode_less_reason="AC138-adversarial: mode 8 hole test, overlap made mode-less"
    )
    monkeypatch.setattr(rule, "mode_declaration", replacement)

    d = traceability.matrix_to_dict(traceability.build_matrix())
    assert d["directions"]["mode_to_rule"]["complete"] is False
    holes = d["directions"]["mode_to_rule"]["holes"]
    assert holes, "expected at least one hole"
    assert any("8" in str(hole) for hole in holes), holes

    mode8 = _mode_record(d, 8)
    assert mode8["rules"] == []


# =========================================================================== #
# AC26: an undeclared registered rule makes rule -> mode fail loudly
# =========================================================================== #


def test_ac26_undeclared_registered_rule_makes_rule_to_mode_fail_loudly(isolated_registry):
    from segfacet.heuristics.rule import Rule, register_rule
    import segfacet.traceability as traceability

    class _NoDeclarationRule(Rule):
        rule_id = "__item138_no_declaration__"

        def evaluate(self, record, config):
            return []

    register_rule(_NoDeclarationRule)  # must not raise

    d = traceability.matrix_to_dict(traceability.build_matrix())
    assert d["directions"]["rule_to_mode"]["complete"] is False
    holes = d["directions"]["rule_to_mode"]["holes"]
    assert holes, "expected at least one hole"
    assert any("__item138_no_declaration__" in str(hole) for hole in holes), holes


# =========================================================================== #
# AC27: a malformed evidence renders as one cell, not one per character
# =========================================================================== #


def test_ac27_bare_string_evidence_renders_as_one_cell_not_per_character(monkeypatch):
    from segfacet.heuristics.rule import _RULES
    import segfacet.heuristics.rule as rule_mod
    import segfacet.traceability as traceability

    rule = _RULES["bounds"]
    # The known item-136 weakness (A6): __post_init__ iterates `evidence`,
    # and a bare str is itself iterable-of-non-empty-strings (its
    # characters), so this construction does not raise.
    replacement = rule_mod.RuleModeDeclaration(modes=(2,), evidence="corpus-derived")
    monkeypatch.setattr(rule, "mode_declaration", replacement)

    matrix = traceability.build_matrix()
    md = traceability.render_markdown(matrix)
    lines = md.splitlines()
    row = _row_for_rule(lines, "bounds")
    assert row is not None, "expected a rendered row for bounds"
    assert "corpus-derived" in row
    assert "c, o, r" not in row


# =========================================================================== #
# AC28: nothing environment-dependent
# =========================================================================== #


def _assert_no_environment_dependent_content(text: str):
    assert not re.search(r"\d{4}-\d{2}-\d{2}", text)
    assert _REPO_ROOT.as_posix() not in text
    assert not re.search(r"[A-Za-z]:\\", text)
    import socket

    hostname = socket.gethostname()
    if hostname:
        assert hostname not in text


def test_ac28_committed_artifacts_carry_nothing_environment_dependent():
    json_text = _COMMITTED_JSON.read_text(encoding="utf-8")
    md_text = _COMMITTED_MD.read_text(encoding="utf-8")

    payload = json.loads(json_text)
    assert payload, "expected a non-empty JSON payload"

    def _walk(node):
        if isinstance(node, float):
            raise AssertionError(f"unexpected float leaf: {node!r}")
        if isinstance(node, dict):
            for value in node.values():
                _walk(value)
        elif isinstance(node, list):
            for value in node:
                _walk(value)

    _walk(payload)

    _assert_no_environment_dependent_content(json_text)
    _assert_no_environment_dependent_content(md_text)


# =========================================================================== #
# AC29: the committed-artifact guard stays clean and unextended
# =========================================================================== #


def test_ac29_committed_artifact_guard_clean_and_grounds_unextended():
    import committed_artifact_guard as guard

    violations = list(guard.iter_violations(_REPO_ROOT / "tests"))
    assert violations == [], [guard.violation_message([v]) for v in violations]
    assert len(guard.GROUNDS) == 5

    for entry in guard.ALLOWLIST:
        assert "traceability_matrix" not in entry.path, entry.path


# =========================================================================== #
# AC30: the matrix is inert at evaluation time
# =========================================================================== #


def test_ac30_build_matrix_is_inert_and_deterministic_at_evaluation_time():
    from segfacet.config import bundled_default_config
    from segfacet.heuristics.runner import run_rules
    from segfacet.pipeline import extract_feature_record
    from segfacet.synth.clean_gt import build_clean_spine
    import segfacet.traceability as traceability

    config = bundled_default_config()
    clean = build_clean_spine()
    record = extract_feature_record(clean.seg_img, config)

    before = run_rules(record, config)
    assert isinstance(before, list)

    matrix_one = traceability.build_matrix()
    d1 = traceability.matrix_to_dict(matrix_one)

    after = run_rules(record, config)
    assert after == before

    matrix_two = traceability.build_matrix()
    d2 = traceability.matrix_to_dict(matrix_two)
    assert d1 == d2


def test_adv_matrix_to_dict_mutation_does_not_leak_into_a_later_call():
    import segfacet.traceability as traceability

    matrix = traceability.build_matrix()
    d1 = traceability.matrix_to_dict(matrix)
    assert d1, "expected a non-empty dict"

    d1["modes"] = "deliberately corrupted by this test"
    d2 = traceability.matrix_to_dict(matrix)
    assert d2["modes"] != "deliberately corrupted by this test"


# =========================================================================== #
# AC31: every mode's mechanism names a resolvable live token; no
# character-count threshold anywhere in this module
# =========================================================================== #


@pytest.mark.parametrize("mode", MODES)
def test_ac31_mode_mechanism_names_a_resolvable_live_token(mode):
    import segfacet.feature_docs as feature_docs_module
    import segfacet.traceability as traceability

    case_ids_for_mode = {c["case_id"] for c in _manifest_cases() if c.get("failure_mode") == mode}

    d = traceability.matrix_to_dict(traceability.build_matrix())
    record = _mode_record(d, mode)
    mechanism = record["mechanism"]
    assert mechanism, mode

    anchors = set(feature_docs_module.MODE_ANCHOR_PATHS[mode])
    rules_for_mode = set(record["rules"])
    assert rules_for_mode, mode

    candidate_tokens = anchors | case_ids_for_mode | rules_for_mode
    assert candidate_tokens, mode
    assert any(_token_in_mechanism(token, mechanism) for token in candidate_tokens), (
        mode,
        mechanism,
        candidate_tokens,
    )


_LENGTH_THRESHOLD_RE = re.compile(r"len\([^)\n]*\)\s*(>=|<=|>|<)\s*\d+")


def test_ac31_no_character_count_threshold_assertions_in_this_module():
    """A14 -- item 137's own defect was exactly this shape (a character-count
    floor standing in for a content check on a mechanism sentence). This
    module inspects its own source and must contain no such pattern for any
    mechanism, rung label, or qualifier string -- or anything else."""
    source = Path(__file__).read_text(encoding="utf-8")
    offenders = _LENGTH_THRESHOLD_RE.findall(source)
    assert offenders == [], offenders


def test_adv_ac31_stale_mechanism_naming_no_live_identifier_is_detectable(monkeypatch):
    import segfacet.feature_docs as feature_docs_module
    import segfacet.traceability as traceability

    case_ids_for_mode8 = {c["case_id"] for c in _manifest_cases() if c.get("failure_mode") == 8}

    bogus_mechanism = (
        "This sentence is deliberately long and describes nothing that "
        "lives in the codebase or the corpus at all, on purpose, for a test."
    )
    _patch_mode_rungs(monkeypatch, traceability, 8, mechanism=bogus_mechanism)

    d = traceability.matrix_to_dict(traceability.build_matrix())
    mode8 = _mode_record(d, 8)
    anchors = set(feature_docs_module.MODE_ANCHOR_PATHS[8])
    rules_for_mode = set(mode8["rules"])
    assert rules_for_mode, "expected mode 8 to still declare at least one rule"

    candidate_tokens = anchors | case_ids_for_mode8 | rules_for_mode
    assert candidate_tokens, "expected at least one live token candidate for mode 8"
    assert not any(_token_in_mechanism(token, mode8["mechanism"]) for token in candidate_tokens)


def test_adv_ac31_stale_mechanism_one_character_off_the_real_case_id_is_detectable(monkeypatch):
    import segfacet.feature_docs as feature_docs_module
    import segfacet.traceability as traceability

    case_ids_for_mode8 = {c["case_id"] for c in _manifest_cases() if c.get("failure_mode") == 8}
    assert case_ids_for_mode8, "expected at least one mode-8 corpus case"
    assert "mode8_force_overlap" in case_ids_for_mode8

    typo_mechanism = (
        "The mechanism names mode8_force_overlaps, one character off the "
        "real case id, on purpose, for a test."
    )
    _patch_mode_rungs(monkeypatch, traceability, 8, mechanism=typo_mechanism)

    d = traceability.matrix_to_dict(traceability.build_matrix())
    mode8 = _mode_record(d, 8)
    anchors = set(feature_docs_module.MODE_ANCHOR_PATHS[8])
    rules_for_mode = set(mode8["rules"])
    assert rules_for_mode, "expected mode 8 to still declare at least one rule"

    candidate_tokens = anchors | case_ids_for_mode8 | rules_for_mode
    assert candidate_tokens, "expected at least one live token candidate for mode 8"
    assert not any(_token_in_mechanism(token, mode8["mechanism"]) for token in candidate_tokens)


# =========================================================================== #
# AC32: mode 1's rule list contains every rule a feature-level derivation
# requires
# =========================================================================== #


def test_ac32_mode1_rule_list_contains_every_feature_derived_required_rule():
    import segfacet.feature_docs as feature_docs_module
    import segfacet.reference.delta as delta_module
    import segfacet.traceability as traceability

    tracked = delta_module.INGESTED_FEATURES
    assert tracked, "expected a non-empty reference_delta tracked-feature vocabulary"

    feature_record_path = {
        name: "per_label.{label}.geometry." + name for name in tracked if name != "spline_offset_mm"
    }
    feature_record_path["spline_offset_mm"] = "stage3.per_label_offsets[].offset_mm"
    assert set(feature_record_path) == set(tracked)

    anchor_modes_by_path: dict = {}
    for mode, paths in feature_docs_module.MODE_ANCHOR_PATHS.items():
        for path in paths:
            anchor_modes_by_path.setdefault(path, set()).add(mode)

    required_modes: set = set()
    for feature_name in tracked:
        required_modes |= anchor_modes_by_path.get(feature_record_path[feature_name], set())
    assert required_modes, "expected at least one tracked feature to map onto a mode anchor"
    assert 1 in required_modes

    d = traceability.matrix_to_dict(traceability.build_matrix())
    for mode in required_modes:
        record = _mode_record(d, mode)
        assert "reference_delta" in record["rules"], (mode, record["rules"])

    reference_delta_record = _rule_records(d)["reference_delta"]
    for mode in required_modes:
        assert mode in reference_delta_record["modes"], (mode, reference_delta_record["modes"])


def test_adv_ac32_renarrowed_reference_delta_declaration_fails_the_matrix_level_check(monkeypatch):
    """The false-premised shape commit b1c593c corrected -- narrowing
    reference_delta back to modes=(2,) must make the matrix under-report
    mode 1's rule list, from the feature-level derivation rather than any
    literal."""
    from segfacet.heuristics.rule import _RULES
    import segfacet.heuristics.rule as rule_mod
    import segfacet.traceability as traceability

    rule = _RULES["reference_delta"]
    narrowed = rule_mod.RuleModeDeclaration(
        modes=(2,), evidence=("analytic", "AC32 adversarial: re-narrowed back to modes=(2,)")
    )
    monkeypatch.setattr(rule, "mode_declaration", narrowed)

    d = traceability.matrix_to_dict(traceability.build_matrix())
    mode1 = _mode_record(d, 1)
    assert "reference_delta" not in mode1["rules"], mode1["rules"]


# =========================================================================== #
# AC33: the mode -> feature list declares its rule granularity
# =========================================================================== #


@pytest.mark.parametrize("mode", MODES)
def test_ac33_mode_feature_list_declares_rule_granularity(mode):
    import segfacet.traceability as traceability

    d = traceability.matrix_to_dict(traceability.build_matrix())
    record = _mode_record(d, mode)
    assert record["granularity"] == "rule", mode
    qualifier = record["feature_paths_qualifier"]
    assert "a rule that targets this mode reads this path" in qualifier, mode


def test_ac33_committed_markdown_prints_the_granularity_qualifier_beside_the_mode_table():
    lines = _md_lines()
    text = "\n".join(lines)

    mode_header_idx = None
    rule_header_idx = None
    for idx, line in enumerate(lines):
        if mode_header_idx is None and "Pipeline-detected" in line:
            mode_header_idx = idx
        if rule_header_idx is None and "Declared modes" in line:
            rule_header_idx = idx
    assert mode_header_idx is not None, "expected a mode table header"
    assert rule_header_idx is not None, "expected a rule table header"
    assert rule_header_idx > mode_header_idx

    section = "\n".join(lines[mode_header_idx:rule_header_idx])
    assert "a rule that targets this mode reads this path" in section
    assert text  # keep the joined text referenced for clarity of the slice above


# =========================================================================== #
# Edge cases
# =========================================================================== #


def test_adv_singleton_declaring_rule_mode_renders_a_well_formed_row():
    """A mode whose declaring-rule set is a singleton (e.g. mode 5, coverage
    only) still renders a well-formed row."""
    import segfacet.traceability as traceability

    d = traceability.matrix_to_dict(traceability.build_matrix())
    mode5 = _mode_record(d, 5)
    assert mode5["rules"] == ["coverage"]
    assert mode5["title"]
    assert mode5["rung"] in RUNGS
    assert mode5["feature_paths"], "expected a non-empty feature-path union for mode 5"


def test_adv_rule_consuming_zero_catalogued_paths_renders_empty_feature_list(isolated_registry):
    """A rule consuming zero catalogued paths renders an empty feature list
    rather than raising."""
    from segfacet.heuristics.rule import Rule, RuleModeDeclaration, register_rule
    import segfacet.traceability as traceability

    class _ZeroReadRule(Rule):
        rule_id = "__item138_zero_read__"
        mode_declaration = RuleModeDeclaration(
            modes=(1,), evidence=("analytic", "AC-adjacent: consumes no catalogued path")
        )

        def evaluate(self, record, config):
            return []

    register_rule(_ZeroReadRule)

    d = traceability.matrix_to_dict(traceability.build_matrix())
    record = _rule_records(d)["__item138_zero_read__"]
    assert record["feature_paths"] == []
