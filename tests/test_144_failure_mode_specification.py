"""Tests for item 144 -- the failure-mode specification module and its
generated rendering (``segfacet.failure_modes``,
``docs/aide/failure_modes.generated.{json,md}``).

Covers Acceptance Criteria AC1-AC24, per the item spec's Testing Strategy
("Per-AC shape"), plus the listed adversarial / edge cases. This item ships a
**minimal seed set of two entries** (modes 3 and 8, A4) -- every rejection
path, every lifecycle-derivation edge case and the multi-edge rung derivation
are exercised on test-constructed ``ModeSpec``s here, never against the
shipped seed, which the spec's A4 states explicitly.

A7 -- this module makes no byte-exact fresh-vs-committed comparison (the
run-to-run byte comparisons are between two ``tmp_path`` renders; the
committed-vs-fresh checks go through ``json.loads`` for the JSON and
substring/section assertions for the Markdown) -- so it adds no entry to
``tests/committed_artifact_guard.py``'s ``ALLOWLIST`` and no new ``GROUNDS``
member.
"""

from __future__ import annotations

import ast
import dataclasses
import json
import re
import sys
from pathlib import Path

import pytest

from run_process import run_utf8

_REPO_ROOT = Path(__file__).resolve().parents[1]
_COMMITTED_JSON = _REPO_ROOT / "docs" / "aide" / "failure_modes.generated.json"
_COMMITTED_MD = _REPO_ROOT / "docs" / "aide" / "failure_modes.generated.md"
_VISION_PATH = _REPO_ROOT / "docs" / "aide" / "vision.md"
_MANIFEST_PATH = _REPO_ROOT / "tests" / "corpus" / "manifest.json"
_FAILURE_MODES_SOURCE = _REPO_ROOT / "src" / "segfacet" / "failure_modes.py"

_HEAVY_ROOTS = {"numpy", "scipy", "nibabel"}


def _top_level_heavy_imports(source):
    """Return the subset of ``{numpy, scipy, nibabel}`` imported at module
    scope in ``source`` (a root package, not a submodule name).

    Walks the module's top-level statements, descending into top-level
    ``try``/``if`` bodies (a defensive ``try: import numpy ... except
    ImportError`` at module scope still counts) but never into a function or
    class body -- a heavy import deferred inside a function is exactly what
    AC1 requires and must not be flagged.
    """
    tree = ast.parse(source)
    found = set()

    def _scan(stmts):
        for node in stmts:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if root in _HEAVY_ROOTS:
                        found.add(root)
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.level == 0:
                    root = node.module.split(".")[0]
                    if root in _HEAVY_ROOTS:
                        found.add(root)
            elif isinstance(node, ast.Try):
                _scan(node.body)
                for handler in node.handlers:
                    _scan(handler.body)
                _scan(node.orelse)
                _scan(node.finalbody)
            elif isinstance(node, ast.If):
                _scan(node.body)
                _scan(node.orelse)

    _scan(tree.body)
    return found


# =========================================================================== #
# House fixtures / helpers
# =========================================================================== #


@pytest.fixture
def isolated_registry():
    """Snapshot/restore the rule registry (the house pattern from
    ``tests/test_026_rule_engine_core.py`` / ``test_136`` / ``test_138``), so
    a stub rule registered for AC9's adversarial coverage cannot leak into
    another test."""
    from segfacet.heuristics.rule import _RULES

    snapshot = dict(_RULES)
    yield
    _RULES.clear()
    _RULES.update(snapshot)


def _measured_expected_firing(case_id: str) -> tuple:
    """The full set of ``rule_id``s a manifest case's detection path fires,
    measured live through the same public harness
    (:mod:`segfacet.synth.regression`) A3 requires -- never transcribed, so
    an adversarial ``ModeSpec`` built from it is guaranteed self-consistent
    regardless of what the pipeline actually fires on this corpus."""
    from segfacet.synth.regression import pipeline_findings, reconstructed_findings

    case = _manifest_case(case_id)
    if case["detection"] == "pipeline":
        findings = pipeline_findings(case)
    elif case["detection"] == "reconstructed_record":
        findings = reconstructed_findings(case)
    else:
        raise AssertionError(f"unrecognised detection for case_id={case_id!r}: {case['detection']!r}")
    firing = tuple(sorted({f.rule_id for f in findings}))
    assert firing, f"expected at least one fired rule_id for case_id={case_id!r}"
    return firing


def _mode3_kwargs(**overrides) -> dict:
    """A valid, self-consistent kwargs dict for mode 3 (``ModeSpec``'s exact
    AC2 field tuple), grounded in the live ``MODE_ANCHOR_PATHS`` and a live
    measurement of the committed geometric corpus -- not transcribed
    values."""
    import segfacet.failure_modes as fm
    import segfacet.feature_docs as feature_docs

    kwargs = dict(
        id=3,
        name="Disconnected components / islands, especially tiny rogue segments",
        definition="A label's foreground voxels split into more than one "
        "connected component, with at least one stray component far smaller "
        "than the dominant body.",
        discriminator="Distinguishes from mode 2 (over-/under-segmentation) "
        "by whether the dominant body itself stays intact.",
        observability="single-channel-observable",
        candidate_features=(
            fm.CandidateFeature(
                path=feature_docs.MODE_ANCHOR_PATHS[3][0],
                role="stage18-metric-anchor",
            ),
        ),
        intended_rules=(
            fm.IntendedRule(
                rule_id="fragmentation",
                detector="",
                evidence_rung="synthetic-demonstrable",
            ),
        ),
        corpus_cases=(
            fm.CorpusCaseExpectation(
                case_id="mode3_inject_islands",
                corpus="geometric",
                expected_firing=_measured_expected_firing("mode3_inject_islands"),
                reason="pipeline-detected, measured on the committed corpus",
            ),
        ),
        severity="flagged-for-review",
        status="specified",
        provenance="hypothesised",
    )
    kwargs.update(overrides)
    return kwargs


def _mode8_kwargs(**overrides) -> dict:
    import segfacet.failure_modes as fm
    import segfacet.feature_docs as feature_docs

    kwargs = dict(
        id=8,
        name="Overlapping segments",
        definition="Two labels' foreground voxel sets intersect.",
        discriminator="Distinguishes from every other mode by requiring a "
        "second label's mask, unobservable from a single label map alone.",
        observability="structurally-unobservable",
        candidate_features=(
            fm.CandidateFeature(
                path=feature_docs.MODE_ANCHOR_PATHS[8][0],
                role="stage18-metric-anchor",
            ),
        ),
        intended_rules=(
            fm.IntendedRule(
                rule_id="overlap",
                detector="",
                evidence_rung="structurally-unobservable",
            ),
        ),
        corpus_cases=(
            fm.CorpusCaseExpectation(
                case_id="mode8_force_overlap",
                corpus="geometric",
                expected_firing=_measured_expected_firing("mode8_force_overlap"),
                reason="reconstructed-record-detected, measured on the committed corpus",
            ),
        ),
        severity="flagged-for-review",
        status="specified",
        provenance="hypothesised",
    )
    kwargs.update(overrides)
    return kwargs


def _manifest_cases() -> list:
    payload = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    cases = payload["cases"]
    assert cases, "expected a non-empty corpus manifest"
    return cases


def _manifest_case(case_id: str) -> dict:
    for case in _manifest_cases():
        if case["case_id"] == case_id:
            return case
    raise AssertionError(f"case_id {case_id!r} not found in the committed manifest")


def _vision_mode_titles() -> dict:
    """Parse vision.md §6's numbered list live -- A10 keeps this parse in the
    test, not in the production module."""
    text = _VISION_PATH.read_text(encoding="utf-8")
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


# =========================================================================== #
# AC1: zero-argument public API, no heavy import
# =========================================================================== #


def test_ac1_public_api_exports():
    import segfacet.failure_modes as fm

    names = (
        "ModeSpec",
        "CandidateFeature",
        "IntendedRule",
        "CorpusCaseExpectation",
        "SPECIFICATION",
        "iter_modes",
        "derive_status",
        "derive_mode_rung",
        "specification_conflicts",
        "specification_to_dict",
        "render_markdown",
        "main",
    )
    for name in names:
        assert hasattr(fm, name), name
        assert name in fm.__all__, name


def test_ac1_zero_argument_calls_accepted(monkeypatch):
    import segfacet.failure_modes as fm

    modes = list(fm.iter_modes())
    assert modes, "expected at least one mode from iter_modes()"

    payload = fm.specification_to_dict()
    assert payload, "expected a non-empty dict from specification_to_dict()"

    calls = []

    def _fake_write_bytes(self, data):
        calls.append(self)
        return len(data)

    monkeypatch.setattr(Path, "write_bytes", _fake_write_bytes)
    fm.main([])
    assert calls, "expected main([]) to attempt at least one write"


def test_ac1_no_module_level_heavy_import():
    """AC1's "no heavy import" clause, honestly scoped: ``failure_modes.py``
    itself has no top-level ``numpy``/``scipy``/``nibabel`` import. A bare
    ``import segfacet.X`` cannot be asserted heavy-module-free at all --
    ``src/segfacet/__init__.py`` unconditionally imports
    ``segfacet.features.fragmentation``, which imports ``nibabel`` at module
    level, before any submodule's own body runs (see this item's Decisions
    log; not a path this item may edit)."""
    source = _FAILURE_MODES_SOURCE.read_text(encoding="utf-8")
    assert source, "expected non-empty source for failure_modes.py"
    heavy = _top_level_heavy_imports(source)
    assert heavy == set(), sorted(heavy)


def test_ac1_heavy_import_helper_flags_a_positive_case():
    """Negative control for the AST helper above: without this, a helper
    that always returns ``set()`` would make the previous test pass while
    checking nothing."""
    snippet = "import numpy\n\n\ndef f():\n    return 1\n"
    heavy = _top_level_heavy_imports(snippet)
    assert heavy == {"numpy"}


def test_ac1_import_adds_no_heavy_module_beyond_the_package_init():
    """``import segfacet.failure_modes`` may load whatever
    ``import segfacet`` already loads (the package init's own cost, out of
    this item's authorised paths) but must add no *further* heavy module."""
    bare = run_utf8(
        [
            sys.executable,
            "-c",
            "import sys, json\nimport segfacet\nprint(json.dumps(sorted(sys.modules)))",
        ],
        cwd=_REPO_ROOT,
        timeout=60,
    )
    assert bare.returncode == 0, bare.stderr
    assert bare.stdout, "expected stdout from the bare-package subprocess"
    bare_loaded = set(json.loads(bare.stdout))

    with_module = run_utf8(
        [
            sys.executable,
            "-c",
            "import sys, json\nimport segfacet.failure_modes\nprint(json.dumps(sorted(sys.modules)))",
        ],
        cwd=_REPO_ROOT,
        timeout=60,
    )
    assert with_module.returncode == 0, with_module.stderr
    assert with_module.stdout, "expected stdout from the failure_modes subprocess"
    module_loaded = set(json.loads(with_module.stdout))

    heavy_bare = {m for m in bare_loaded if m.split(".")[0] in _HEAVY_ROOTS}
    heavy_module = {m for m in module_loaded if m.split(".")[0] in _HEAVY_ROOTS}
    assert heavy_bare, "expected the bare package import to already load a heavy module"
    assert heavy_module == heavy_bare, (
        sorted(heavy_module - heavy_bare),
        sorted(heavy_bare - heavy_module),
    )


# =========================================================================== #
# AC2: ModeSpec is a frozen dataclass with exactly §6's fields
# =========================================================================== #


def test_ac2_field_names_are_exactly_section_six_fields():
    import segfacet.failure_modes as fm

    names = tuple(f.name for f in dataclasses.fields(fm.ModeSpec))
    assert names == (
        "id",
        "name",
        "definition",
        "discriminator",
        "observability",
        "candidate_features",
        "intended_rules",
        "corpus_cases",
        "severity",
        "status",
        "provenance",
    )


def test_ac2_is_frozen_dataclass():
    import segfacet.failure_modes as fm

    assert dataclasses.is_dataclass(fm.ModeSpec)
    assert fm.ModeSpec.__dataclass_params__.frozen is True


def test_ac2_frozen_instance_rejects_attribute_assignment():
    import segfacet.failure_modes as fm

    mode = fm.ModeSpec(**_mode3_kwargs())
    with pytest.raises(dataclasses.FrozenInstanceError):
        mode.name = "renamed"  # type: ignore[misc]


# =========================================================================== #
# AC3: a missing/empty required field is rejected, naming mode and field
# =========================================================================== #


_AC3_STRING_FIELDS = (
    "name",
    "definition",
    "discriminator",
    "observability",
    "severity",
    "status",
    "provenance",
)


@pytest.mark.parametrize("field_name", _AC3_STRING_FIELDS)
def test_ac3_empty_required_string_field_raises_naming_mode_and_field(field_name):
    import segfacet.failure_modes as fm

    kwargs = _mode3_kwargs(**{field_name: ""})
    with pytest.raises(ValueError) as excinfo:
        fm.ModeSpec(**kwargs)
    message = str(excinfo.value)
    assert message.strip()
    assert "3" in message
    assert field_name in message


@pytest.mark.parametrize(
    "id_value",
    [
        pytest.param(None, id="id_none"),
        pytest.param(0, id="id_zero"),
        pytest.param(-1, id="id_negative"),
        pytest.param("3", id="id_non_int"),
        pytest.param(3.0, id="id_float"),
    ],
)
def test_ac3_invalid_id_raises_naming_name_and_field(id_value):
    import segfacet.failure_modes as fm

    kwargs = _mode3_kwargs(id=id_value)
    with pytest.raises(ValueError) as excinfo:
        fm.ModeSpec(**kwargs)
    message = str(excinfo.value)
    assert message.strip()
    assert kwargs["name"] in message
    assert "id" in message


# =========================================================================== #
# AC4: the status vocabulary is closed at four members
# =========================================================================== #


def test_ac4_statuses_vocabulary_is_exactly_four_members():
    import segfacet.failure_modes as fm

    assert fm.STATUSES == ("proposed", "specified", "implemented", "validated")


def test_ac4_status_outside_vocabulary_raises_naming_mode_and_status():
    import segfacet.failure_modes as fm

    kwargs = _mode3_kwargs(status="not-a-real-status")
    with pytest.raises(ValueError) as excinfo:
        fm.ModeSpec(**kwargs)
    message = str(excinfo.value)
    assert "3" in message
    assert "status" in message


@pytest.mark.parametrize("status", ["proposed", "specified"])
def test_ac4_authored_status_members_are_accepted(status):
    import segfacet.failure_modes as fm

    mode = fm.ModeSpec(**_mode3_kwargs(status=status))
    assert mode.status == status


# =========================================================================== #
# AC5: the observability vocabulary is closed at three members
# =========================================================================== #


def test_ac5_observability_vocabulary_is_exactly_three_members():
    import segfacet.failure_modes as fm

    assert fm.OBSERVABILITY == (
        "single-channel-observable",
        "needs-paired-scan",
        "structurally-unobservable",
    )


def test_ac5_observability_outside_vocabulary_raises_naming_mode_and_field():
    import segfacet.failure_modes as fm

    kwargs = _mode3_kwargs(observability="not-a-real-observability")
    with pytest.raises(ValueError) as excinfo:
        fm.ModeSpec(**kwargs)
    message = str(excinfo.value)
    assert "3" in message
    assert "observability" in message


@pytest.mark.parametrize(
    "value",
    ["single-channel-observable", "needs-paired-scan", "structurally-unobservable"],
)
def test_ac5_each_observability_member_is_accepted(value):
    import segfacet.failure_modes as fm

    mode = fm.ModeSpec(**_mode3_kwargs(observability=value))
    assert mode.observability == value


# =========================================================================== #
# AC6: the provenance vocabulary is closed at two members
# =========================================================================== #


def test_ac6_provenance_vocabulary_is_exactly_two_members():
    import segfacet.failure_modes as fm

    assert fm.PROVENANCE == ("hypothesised", "discovered")


def test_ac6_provenance_outside_vocabulary_raises_naming_mode_and_field():
    import segfacet.failure_modes as fm

    kwargs = _mode3_kwargs(provenance="not-a-real-provenance")
    with pytest.raises(ValueError) as excinfo:
        fm.ModeSpec(**kwargs)
    message = str(excinfo.value)
    assert "3" in message
    assert "provenance" in message


@pytest.mark.parametrize("value", ["hypothesised", "discovered"])
def test_ac6_each_provenance_member_is_accepted(value):
    import segfacet.failure_modes as fm

    mode = fm.ModeSpec(**_mode3_kwargs(provenance=value))
    assert mode.provenance == value


# =========================================================================== #
# AC7: every tuple-typed field rejects a bare string and a list
# =========================================================================== #


def test_ac7_candidate_features_bare_string_rejected():
    import segfacet.failure_modes as fm

    kwargs = _mode3_kwargs(candidate_features="not-a-tuple")
    with pytest.raises(ValueError) as excinfo:
        fm.ModeSpec(**kwargs)
    message = str(excinfo.value)
    assert "3" in message
    assert "candidate_features" in message


def test_ac7_candidate_features_list_rejected():
    import segfacet.failure_modes as fm

    valid = _mode3_kwargs()["candidate_features"]
    kwargs = _mode3_kwargs(candidate_features=list(valid))
    with pytest.raises(ValueError) as excinfo:
        fm.ModeSpec(**kwargs)
    message = str(excinfo.value)
    assert "3" in message
    assert "candidate_features" in message


def test_ac7_intended_rules_bare_string_rejected():
    import segfacet.failure_modes as fm

    kwargs = _mode3_kwargs(intended_rules="fragmentation")
    with pytest.raises(ValueError) as excinfo:
        fm.ModeSpec(**kwargs)
    message = str(excinfo.value)
    assert "3" in message
    assert "intended_rules" in message


def test_ac7_intended_rules_list_rejected():
    import segfacet.failure_modes as fm

    valid = _mode3_kwargs()["intended_rules"]
    kwargs = _mode3_kwargs(intended_rules=list(valid))
    with pytest.raises(ValueError) as excinfo:
        fm.ModeSpec(**kwargs)
    message = str(excinfo.value)
    assert "3" in message
    assert "intended_rules" in message


def test_ac7_corpus_cases_bare_string_rejected():
    import segfacet.failure_modes as fm

    kwargs = _mode3_kwargs(corpus_cases="mode3_inject_islands")
    with pytest.raises(ValueError) as excinfo:
        fm.ModeSpec(**kwargs)
    message = str(excinfo.value)
    assert "3" in message
    assert "corpus_cases" in message


def test_ac7_corpus_cases_list_rejected():
    import segfacet.failure_modes as fm

    valid = _mode3_kwargs()["corpus_cases"]
    kwargs = _mode3_kwargs(corpus_cases=list(valid))
    with pytest.raises(ValueError) as excinfo:
        fm.ModeSpec(**kwargs)
    message = str(excinfo.value)
    assert "3" in message
    assert "corpus_cases" in message


def test_ac7_expected_firing_bare_string_rejected_not_split_character_wise():
    """A forgotten pair of parentheses on ``expected_firing=("border",)``
    written as ``expected_firing="border"`` must never silently iterate the
    string character-wise -- the ``RuleModeDeclaration`` weakness recorded in
    ``insights.md``, item 136, 2026-09-02."""
    import segfacet.failure_modes as fm

    kwargs = _mode3_kwargs(
        corpus_cases=(
            fm.CorpusCaseExpectation(
                case_id="mode3_inject_islands",
                corpus="geometric",
                expected_firing="border",
                reason="adversarial: bare string, must not split into 'b','o','r','d','e','r'",
            ),
        )
    )
    with pytest.raises(ValueError) as excinfo:
        fm.ModeSpec(**kwargs)
    message = str(excinfo.value)
    assert "3" in message
    assert "expected_firing" in message


def test_ac7_expected_firing_list_rejected():
    import segfacet.failure_modes as fm

    kwargs = _mode3_kwargs(
        corpus_cases=(
            fm.CorpusCaseExpectation(
                case_id="mode3_inject_islands",
                corpus="geometric",
                expected_firing=["fragmentation"],
                reason="adversarial: list, not tuple",
            ),
        )
    )
    with pytest.raises(ValueError) as excinfo:
        fm.ModeSpec(**kwargs)
    message = str(excinfo.value)
    assert "3" in message
    assert "expected_firing" in message


# =========================================================================== #
# AC8: status is authored only for proposed and specified
# =========================================================================== #


@pytest.mark.parametrize("status", ["implemented", "validated"])
def test_ac8_derived_only_status_rejected_at_construction(status):
    import segfacet.failure_modes as fm

    kwargs = _mode3_kwargs(status=status)
    with pytest.raises(ValueError) as excinfo:
        fm.ModeSpec(**kwargs)
    message = str(excinfo.value)
    assert "3" in message
    assert "status" in message


# =========================================================================== #
# AC9: implemented is derived from the live registry
# =========================================================================== #


def test_ac9_derive_status_implemented_iff_a_registered_rule_declares_the_mode(
    isolated_registry,
):
    import segfacet.failure_modes as fm
    from segfacet.heuristics.rule import Rule, RuleModeDeclaration, _RULES, register_rule

    # No corpus_cases so derive_status cannot reach "validated" via that path.
    mode = fm.ModeSpec(**_mode3_kwargs(corpus_cases=()))
    assert fm.derive_status(mode) == "specified"

    class _FakeFragmentationDetector(Rule):
        rule_id = "__item144_fake_mode3_detector__"
        mode_declaration = RuleModeDeclaration(modes=(3,), evidence=("analytic",))

        def evaluate(self, record, config):
            return []

    register_rule(_FakeFragmentationDetector)
    assert fm.derive_status(mode) == "implemented"

    del _RULES["__item144_fake_mode3_detector__"]
    assert fm.derive_status(mode) == "specified"


# =========================================================================== #
# AC10: validated is derived from a live corpus measurement
# =========================================================================== #


def test_ac10_derive_status_validated_iff_every_corpus_case_measured_matches():
    import segfacet.failure_modes as fm

    mode = fm.ModeSpec(**_mode3_kwargs())
    assert fm.derive_status(mode) == "validated"


def test_ac10_wrong_expected_firing_drops_validated_to_implemented():
    import segfacet.failure_modes as fm

    wrong_case = fm.CorpusCaseExpectation(
        case_id="mode3_inject_islands",
        corpus="geometric",
        expected_firing=("__item144_no_such_rule_ever_fires__",),
        reason="adversarial: deliberately wrong expected_firing",
    )
    mode = fm.ModeSpec(**_mode3_kwargs(corpus_cases=(wrong_case,)))
    assert fm.derive_status(mode) == "implemented"

    conflicts = fm.specification_conflicts()
    # The shipped SPECIFICATION disagrees with nothing; this adversarial
    # ModeSpec is test-constructed and not part of it, so we assert the
    # *mechanism* (case_agrees) directly rather than expecting it to appear
    # in specification_conflicts() for the shipped spec.
    assert fm.case_agrees(wrong_case) is False


def test_adv_expected_firing_empty_on_case_that_fires_something_is_disagreement():
    import segfacet.failure_modes as fm

    empty_case = fm.CorpusCaseExpectation(
        case_id="mode3_inject_islands",
        corpus="geometric",
        expected_firing=(),
        reason="adversarial: empty expected_firing against a case that fires",
    )
    assert fm.case_agrees(empty_case) is False
    mode = fm.ModeSpec(**_mode3_kwargs(corpus_cases=(empty_case,)))
    assert fm.derive_status(mode) == "implemented"


def test_adv_empty_corpus_cases_and_intended_rules_derives_specified_not_validated():
    """The empty set must never satisfy an "every case agrees" quantifier
    vacuously into a stronger status."""
    import segfacet.failure_modes as fm

    mode = fm.ModeSpec(**_mode3_kwargs(intended_rules=(), corpus_cases=()))
    assert fm.derive_status(mode) == "specified"


# =========================================================================== #
# AC11: a hand-set derived status is reported by the conformance check
# =========================================================================== #


def test_ac11_shipped_specification_has_no_conflicts():
    import segfacet.failure_modes as fm

    assert fm.specification_conflicts() == ()


def test_ac11_forced_status_past_post_init_is_reported_naming_the_mode():
    import segfacet.failure_modes as fm

    mode = fm.ModeSpec(**_mode3_kwargs())
    object.__setattr__(mode, "status", "implemented")

    conflicts = fm.specification_conflicts((mode,))
    assert len(conflicts) == 1
    assert "3" in conflicts[0]
    assert "status" in conflicts[0]


# =========================================================================== #
# AC12: candidate feature carries a role; stage18-metric-anchor validated
# =========================================================================== #


def test_ac12_candidate_roles_vocabulary():
    import segfacet.failure_modes as fm

    assert fm.CANDIDATE_ROLES == ("stage18-metric-anchor", "hypothesised")


def test_ac12_role_outside_vocabulary_raises_naming_mode_and_path():
    import segfacet.failure_modes as fm

    bad_feature = fm.CandidateFeature(path="per_label.{label}.geometry.touches_left", role="bogus")
    kwargs = _mode3_kwargs(candidate_features=(bad_feature,))
    with pytest.raises(ValueError) as excinfo:
        fm.ModeSpec(**kwargs)
    message = str(excinfo.value)
    assert "3" in message
    assert bad_feature.path in message


def test_ac12_anchor_path_not_in_mode_anchor_paths_raises_naming_all_three():
    """A near-miss of the real anchor path (one segment renamed) -- the
    exact near-miss shape that silently disabled item 136's "corpus" tag
    check -- is rejected, not silently accepted."""
    import segfacet.failure_modes as fm

    near_miss_path = "per_label.{label}.components.stray_component_size[]"  # missing 's'
    bad_feature = fm.CandidateFeature(path=near_miss_path, role="stage18-metric-anchor")
    kwargs = _mode3_kwargs(candidate_features=(bad_feature,))
    with pytest.raises(ValueError) as excinfo:
        fm.ModeSpec(**kwargs)
    message = str(excinfo.value)
    assert "3" in message
    assert near_miss_path in message
    assert "stray_component_sizes" in message  # names the anchor set it was checked against


def test_ac12_valid_anchor_path_is_accepted():
    import segfacet.failure_modes as fm

    mode = fm.ModeSpec(**_mode3_kwargs())
    assert mode.candidate_features[0].role == "stage18-metric-anchor"


def test_adv_mode_id_absent_from_mode_anchor_paths_raises_naming_mode_not_keyerror():
    import segfacet.failure_modes as fm

    bad_feature = fm.CandidateFeature(
        path="per_label.{label}.components.stray_component_sizes[]",
        role="stage18-metric-anchor",
    )
    kwargs = _mode3_kwargs(id=999, candidate_features=(bad_feature,), name="not a real mode")
    # A KeyError from an un-guarded MODE_ANCHOR_PATHS[999] lookup would also
    # satisfy a bare `with pytest.raises(Exception)`, so pin ValueError
    # specifically -- naming the mode, not crashing on the missing key.
    with pytest.raises(ValueError) as excinfo:
        fm.ModeSpec(**kwargs)
    message = str(excinfo.value)
    assert "999" in message


# =========================================================================== #
# AC13: every mode<->rule edge carries a rung from the closed vocabulary
# =========================================================================== #


def test_ac13_evidence_rungs_vocabulary():
    import segfacet.failure_modes as fm

    assert fm.EVIDENCE_RUNGS == (
        "synthetic-demonstrable",
        "needs-real-data",
        "structurally-unobservable",
    )


def test_ac13_rung_outside_vocabulary_raises_naming_mode_and_rule_id():
    import segfacet.failure_modes as fm

    bad_rule = fm.IntendedRule(rule_id="fragmentation", detector="", evidence_rung="not-a-rung")
    kwargs = _mode3_kwargs(intended_rules=(bad_rule,))
    with pytest.raises(ValueError) as excinfo:
        fm.ModeSpec(**kwargs)
    message = str(excinfo.value)
    assert "3" in message
    assert "fragmentation" in message


def test_ac13_empty_rule_id_raises_naming_mode_and_rule_id():
    import segfacet.failure_modes as fm

    bad_rule = fm.IntendedRule(rule_id="", detector="", evidence_rung="synthetic-demonstrable")
    kwargs = _mode3_kwargs(intended_rules=(bad_rule,))
    with pytest.raises(ValueError) as excinfo:
        fm.ModeSpec(**kwargs)
    message = str(excinfo.value)
    assert "3" in message


def test_ac13_detector_may_be_empty():
    import segfacet.failure_modes as fm

    rule = fm.IntendedRule(rule_id="fragmentation", detector="", evidence_rung="synthetic-demonstrable")
    mode = fm.ModeSpec(**_mode3_kwargs(intended_rules=(rule,)))
    assert mode.intended_rules[0].detector == ""


@pytest.mark.parametrize(
    "rung", ["synthetic-demonstrable", "needs-real-data", "structurally-unobservable"]
)
def test_ac13_each_rung_member_is_accepted(rung):
    import segfacet.failure_modes as fm

    rule = fm.IntendedRule(rule_id="fragmentation", detector="", evidence_rung=rung)
    mode = fm.ModeSpec(**_mode3_kwargs(intended_rules=(rule,)))
    assert mode.intended_rules[0].evidence_rung == rung


def test_adv_duplicate_rule_id_within_intended_rules_rejected():
    import segfacet.failure_modes as fm

    rules = (
        fm.IntendedRule(rule_id="fragmentation", detector="", evidence_rung="synthetic-demonstrable"),
        fm.IntendedRule(rule_id="fragmentation", detector="", evidence_rung="needs-real-data"),
    )
    kwargs = _mode3_kwargs(intended_rules=rules)
    with pytest.raises(ValueError) as excinfo:
        fm.ModeSpec(**kwargs)
    message = str(excinfo.value)
    assert "3" in message
    assert "fragmentation" in message


def test_adv_duplicate_case_id_within_corpus_cases_rejected():
    import segfacet.failure_modes as fm

    cases = (
        fm.CorpusCaseExpectation(
            case_id="mode3_inject_islands",
            corpus="geometric",
            expected_firing=("fragmentation",),
            reason="first",
        ),
        fm.CorpusCaseExpectation(
            case_id="mode3_inject_islands",
            corpus="geometric",
            expected_firing=("fragmentation",),
            reason="duplicate",
        ),
    )
    kwargs = _mode3_kwargs(corpus_cases=cases)
    with pytest.raises(ValueError) as excinfo:
        fm.ModeSpec(**kwargs)
    message = str(excinfo.value)
    assert "3" in message
    assert "mode3_inject_islands" in message


# =========================================================================== #
# AC14: a mode's rung is derived as the strongest of its edges
# =========================================================================== #


def test_ac14_derive_mode_rung_is_the_strongest_edge():
    import segfacet.failure_modes as fm

    rules = (
        fm.IntendedRule(rule_id="a", detector="", evidence_rung="structurally-unobservable"),
        fm.IntendedRule(rule_id="b", detector="", evidence_rung="needs-real-data"),
        fm.IntendedRule(rule_id="c", detector="", evidence_rung="synthetic-demonstrable"),
    )
    mode = fm.ModeSpec(**_mode3_kwargs(intended_rules=rules, corpus_cases=()))
    assert fm.derive_mode_rung(mode) == "synthetic-demonstrable"


def test_ac14_weakening_the_strongest_edge_changes_the_derived_rung():
    import segfacet.failure_modes as fm

    rules = (
        fm.IntendedRule(rule_id="a", detector="", evidence_rung="structurally-unobservable"),
        fm.IntendedRule(rule_id="b", detector="", evidence_rung="needs-real-data"),
        fm.IntendedRule(rule_id="c", detector="", evidence_rung="synthetic-demonstrable"),
    )
    mode = fm.ModeSpec(**_mode3_kwargs(intended_rules=rules, corpus_cases=()))
    before = fm.derive_mode_rung(mode)

    weakened_rules = (
        fm.IntendedRule(rule_id="a", detector="", evidence_rung="structurally-unobservable"),
        fm.IntendedRule(rule_id="b", detector="", evidence_rung="needs-real-data"),
        fm.IntendedRule(rule_id="c", detector="", evidence_rung="needs-real-data"),
    )
    mode2 = fm.ModeSpec(**_mode3_kwargs(intended_rules=weakened_rules, corpus_cases=()))
    after = fm.derive_mode_rung(mode2)
    assert after != before
    assert after == "needs-real-data"


def test_ac14_zero_edge_mode_derives_none():
    import segfacet.failure_modes as fm

    mode = fm.ModeSpec(**_mode3_kwargs(intended_rules=(), corpus_cases=()))
    assert fm.derive_mode_rung(mode) is None


# =========================================================================== #
# AC15: the severity vocabulary is derived from Severity, not hand-typed
# =========================================================================== #


def test_ac15_accepted_severities_equal_severity_labels_minus_pass():
    import segfacet.verdict as verdict

    expected = {s.label for s in verdict.Severity} - {"pass"}
    assert expected == {"flagged-for-review", "fail"}


def test_ac15_pass_severity_rejected():
    import segfacet.failure_modes as fm

    kwargs = _mode3_kwargs(severity="pass")
    with pytest.raises(ValueError) as excinfo:
        fm.ModeSpec(**kwargs)
    message = str(excinfo.value)
    assert "3" in message
    assert "severity" in message


def test_ac15_nonmember_severity_rejected():
    import segfacet.failure_modes as fm

    kwargs = _mode3_kwargs(severity="catastrophic")
    with pytest.raises(ValueError) as excinfo:
        fm.ModeSpec(**kwargs)
    message = str(excinfo.value)
    assert "3" in message
    assert "severity" in message


@pytest.mark.parametrize("severity", ["flagged-for-review", "fail"])
def test_ac15_each_accepted_severity_is_accepted(severity):
    import segfacet.failure_modes as fm

    mode = fm.ModeSpec(**_mode3_kwargs(severity=severity))
    assert mode.severity == severity


# =========================================================================== #
# AC16: the shipped seed is exactly two entries, grounded in vision.md §6
# =========================================================================== #


def test_ac16_specification_carries_exactly_modes_three_and_eight():
    import segfacet.failure_modes as fm

    ids = tuple(m.id for m in fm.iter_modes())
    assert ids == (3, 8)


@pytest.mark.parametrize("mode_id", [3, 8])
def test_ac16_every_field_non_empty(mode_id):
    import segfacet.failure_modes as fm

    mode = next(m for m in fm.iter_modes() if m.id == mode_id)
    for field in dataclasses.fields(mode):
        value = getattr(mode, field.name)
        assert value not in ("", (), None), field.name
    assert mode.intended_rules
    assert mode.corpus_cases


@pytest.mark.parametrize("mode_id", [3, 8])
def test_ac16_each_id_is_a_key_of_mode_anchor_paths(mode_id):
    import segfacet.failure_modes as fm
    import segfacet.feature_docs as feature_docs

    mode = next(m for m in fm.iter_modes() if m.id == mode_id)
    assert mode.id in feature_docs.MODE_ANCHOR_PATHS


def test_ac16_names_match_vision_section_six_parsed_titles():
    import segfacet.failure_modes as fm

    titles = _vision_mode_titles()
    assert titles
    for mode in fm.iter_modes():
        assert mode.id in titles, mode.id
        assert mode.name == titles[mode.id], (mode.id, mode.name, titles[mode.id])


# =========================================================================== #
# AC17: zero-argument regeneration writes the two committed paths; redirected
# run leaves them untouched
# =========================================================================== #


def test_ac17_main_no_args_writes_exactly_the_two_committed_paths(monkeypatch):
    import segfacet.failure_modes as fm

    calls = []

    def _fake_write_bytes(self, data):
        calls.append(self)
        return len(data)

    monkeypatch.setattr(Path, "write_bytes", _fake_write_bytes)
    fm.main([])

    assert calls, "expected main([]) to attempt at least one write"
    written = {p.as_posix() for p in calls}
    assert len(written) == 2, written
    assert any(p.endswith("docs/aide/failure_modes.generated.json") for p in written), written
    assert any(p.endswith("docs/aide/failure_modes.generated.md") for p in written), written


def test_ac17_redirected_run_leaves_committed_artifacts_untouched(tmp_path):
    import segfacet.failure_modes as fm

    before_json = _COMMITTED_JSON.read_bytes()
    before_md = _COMMITTED_MD.read_bytes()
    assert before_json, "expected a non-empty committed JSON artifact"
    assert before_md, "expected a non-empty committed markdown artifact"

    json_dest = tmp_path / "out.json"
    md_dest = tmp_path / "out.md"
    fm.main(["--json", str(json_dest), "--md", str(md_dest)])

    assert json_dest.exists()
    assert md_dest.exists()

    after_json = _COMMITTED_JSON.read_bytes()
    after_md = _COMMITTED_MD.read_bytes()
    assert after_json == before_json
    assert after_md == before_md


# =========================================================================== #
# AC18: both artifacts are byte-identical run-to-run (run-to-run only, A7)
# =========================================================================== #


def test_ac18_artifacts_are_byte_reproducible_run_to_run(tmp_path):
    import segfacet.failure_modes as fm

    json_a, md_a = tmp_path / "a.json", tmp_path / "a.md"
    json_b, md_b = tmp_path / "b.json", tmp_path / "b.md"

    fm.main(["--json", str(json_a), "--md", str(md_a)])
    fm.main(["--json", str(json_b), "--md", str(md_b)])

    bytes_a_json, bytes_b_json = json_a.read_bytes(), json_b.read_bytes()
    bytes_a_md, bytes_b_md = md_a.read_bytes(), md_b.read_bytes()
    assert bytes_a_json, "expected non-empty JSON output"
    assert bytes_a_md, "expected non-empty markdown output"

    assert bytes_a_json == bytes_b_json
    assert bytes_a_md == bytes_b_md


# =========================================================================== #
# AC19: the committed JSON is a fresh build; authored/derived status carried
# separately
# =========================================================================== #


def test_ac19_committed_json_parses_to_a_fresh_build():
    import segfacet.failure_modes as fm

    committed_payload = json.loads(_COMMITTED_JSON.read_text(encoding="utf-8"))
    assert committed_payload, "expected a non-empty committed JSON payload"

    fresh_payload = fm.specification_to_dict()
    normalised_fresh = json.loads(json.dumps(fresh_payload, sort_keys=True))
    assert normalised_fresh == committed_payload


def test_ac19_every_mode_carries_status_authored_and_status_derived():
    import segfacet.failure_modes as fm

    payload = fm.specification_to_dict()
    modes = payload["modes"]
    assert modes, "expected at least one mode in specification_to_dict()"
    for mode_record in modes:
        assert mode_record["status_authored"] in ("proposed", "specified")
        assert mode_record["status_derived"] in fm.STATUSES
        for case_record in mode_record["corpus_cases"]:
            assert isinstance(case_record["expected_firing"], list)
            assert isinstance(case_record["agrees"], bool)


# =========================================================================== #
# AC20: the committed Markdown agrees with the committed JSON, entry by entry
# =========================================================================== #


def test_ac20_markdown_carries_every_json_field_per_mode():
    committed_payload = json.loads(_COMMITTED_JSON.read_text(encoding="utf-8"))
    md_text = _COMMITTED_MD.read_text(encoding="utf-8")
    assert md_text, "expected non-empty committed markdown"

    modes = committed_payload["modes"]
    assert modes, "expected at least one mode in the committed JSON"
    for mode_record in modes:
        assert str(mode_record["id"]) in md_text, mode_record["id"]
        assert mode_record["name"] in md_text, mode_record["id"]
        assert mode_record["status_derived"] in md_text, mode_record["id"]
        assert mode_record["observability"] in md_text, mode_record["id"]
        assert mode_record["severity"] in md_text, mode_record["id"]
        assert mode_record["provenance"] in md_text, mode_record["id"]
        for rule_record in mode_record["intended_rules"]:
            assert rule_record["rule_id"] in md_text, mode_record["id"]
            assert rule_record["evidence_rung"] in md_text, mode_record["id"]
        for case_record in mode_record["corpus_cases"]:
            for rule_id in case_record["expected_firing"]:
                assert rule_id in md_text, (mode_record["id"], rule_id)


def test_ac20_stage18_anchor_role_rendered_as_metric_path_not_rule_read():
    committed_payload = json.loads(_COMMITTED_JSON.read_text(encoding="utf-8"))
    md_text = _COMMITTED_MD.read_text(encoding="utf-8")

    modes = committed_payload["modes"]
    assert modes
    checked = False
    for mode_record in modes:
        for feature_record in mode_record["candidate_features"]:
            if feature_record["role"] != "stage18-metric-anchor":
                continue
            checked = True
            assert feature_record["path"] in md_text, feature_record["path"]
            # The path must be rendered under a role label naming the metric
            # anchor, never as a generic "rule read" path.
            idx = md_text.find(feature_record["path"])
            window = md_text[max(0, idx - 200) : idx + 200].lower()
            assert "metric" in window or "stage18" in window or "anchor" in window, window
    assert checked, "expected at least one stage18-metric-anchor candidate feature"


# =========================================================================== #
# AC21: both artifacts are LF bytes, one trailing newline, written via
# write_bytes
# =========================================================================== #


def test_ac21_both_artifacts_are_lf_bytes_with_one_trailing_newline():
    for path in (_COMMITTED_JSON, _COMMITTED_MD):
        data = path.read_bytes()
        assert data, path
        assert b"\r" not in data, path
        assert data.endswith(b"\n"), path
        assert not data.endswith(b"\n\n"), path


def test_ac21_main_writes_through_write_bytes_even_if_write_text_raises(monkeypatch, tmp_path):
    import segfacet.failure_modes as fm

    def _raising_write_text(self, *args, **kwargs):
        raise AssertionError(f"write_text must never be called (path={self})")

    monkeypatch.setattr(Path, "write_text", _raising_write_text)

    json_dest = tmp_path / "out.json"
    md_dest = tmp_path / "out.md"
    fm.main(["--json", str(json_dest), "--md", str(md_dest)])

    assert json_dest.read_bytes()
    assert md_dest.read_bytes()


# =========================================================================== #
# AC22: .gitattributes pins both new paths text eol=lf
# =========================================================================== #


def test_ac22_gitattributes_pins_both_new_paths_eol_lf():
    text = (_REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")
    for rel_path in (
        "docs/aide/failure_modes.generated.json",
        "docs/aide/failure_modes.generated.md",
    ):
        pattern = re.compile(re.escape(rel_path) + r"[^\n]*eol=lf")
        assert pattern.search(text), rel_path


# =========================================================================== #
# AC23: no stray status icon introduced under docs/aide/
# =========================================================================== #


def _aide_module():
    import importlib.util

    aide_script = _REPO_ROOT / ".aide" / "scripts" / "aide.py"
    spec = importlib.util.spec_from_file_location("_aide_cli_144", aide_script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def test_ac23_no_stray_status_icon_warnings_in_docs_aide():
    aide = _aide_module()
    warnings = aide.stray_icon_warnings(_REPO_ROOT / "docs" / "aide")
    assert warnings == [], warnings


def test_ac23_status_rendered_as_word_not_icon():
    md_text = _COMMITTED_MD.read_text(encoding="utf-8")
    committed_payload = json.loads(_COMMITTED_JSON.read_text(encoding="utf-8"))

    statuses_present = {
        m["status_authored"] for m in committed_payload["modes"]
    } | {m["status_derived"] for m in committed_payload["modes"]}
    assert statuses_present, "expected at least one status value in the committed JSON"
    for status in statuses_present:
        assert status in md_text, status

    # None of the six AIDE status icons should appear anywhere in the
    # rendering -- lifecycle status is a word, never one of the icons read
    # at structural positions elsewhere under docs/aide/
    # (.aide/conventions/1-format-contract/status-icons.md).
    for icon in ("📋", "🚧", "🔍", "✅", "⏸️", "❌"):
        assert icon not in md_text


# =========================================================================== #
# AC24: the specification is immutable and deterministically ordered
# =========================================================================== #


def test_ac24_specification_is_immutable_container():
    import types

    import segfacet.failure_modes as fm

    assert isinstance(fm.SPECIFICATION, (types.MappingProxyType, tuple))


def test_ac24_iter_modes_ascending_by_id():
    import segfacet.failure_modes as fm

    ids = [m.id for m in fm.iter_modes()]
    assert ids == sorted(ids)
    assert ids, "expected at least one mode"


def test_ac24_two_specification_to_dict_calls_are_equal_and_side_effect_free():
    import segfacet.failure_modes as fm
    from segfacet.heuristics.rule import _RULES

    registry_before = dict(_RULES)
    first = fm.specification_to_dict()
    second = fm.specification_to_dict()
    assert first == second
    assert dict(_RULES) == registry_before

    # Mutating the returned dict must not leak into a later call.
    first["modes"] = "deliberately corrupted by this test"
    third = fm.specification_to_dict()
    assert third["modes"] != "deliberately corrupted by this test"


def test_adv_specification_to_dict_before_and_after_a_consumer_call_no_cached_state_leaks():
    import segfacet.failure_modes as fm

    before = fm.specification_to_dict()
    fm.render_markdown()
    after = fm.specification_to_dict()
    assert before == after


# =========================================================================== #
# Adversarial: determinism of main() across two full runs
# =========================================================================== #


def test_adv_main_called_twice_is_deterministic(tmp_path):
    import segfacet.failure_modes as fm

    dest_a_json, dest_a_md = tmp_path / "1a.json", tmp_path / "1a.md"
    dest_b_json, dest_b_md = tmp_path / "1b.json", tmp_path / "1b.md"

    fm.main(["--json", str(dest_a_json), "--md", str(dest_a_md)])
    fm.main(["--json", str(dest_b_json), "--md", str(dest_b_md)])

    assert dest_a_json.read_bytes() == dest_b_json.read_bytes()
    assert dest_a_md.read_bytes() == dest_b_md.read_bytes()


# =========================================================================== #
# Adversarial: measured_firing / case_agrees driven by real corpus cases,
# using the same public harness AC9/AC10 exercise (A3)
# =========================================================================== #


def test_adv_seed_mode3_corpus_case_is_pipeline_detected_and_measured_live():
    import segfacet.failure_modes as fm

    case = _manifest_case("mode3_inject_islands")
    assert case["detection"] == "pipeline"

    mode = next(m for m in fm.iter_modes() if m.id == 3)
    assert len(mode.corpus_cases) >= 1
    case_expectation = next(c for c in mode.corpus_cases if c.case_id == "mode3_inject_islands")
    measured = fm.measured_firing(case_expectation)
    assert measured, "expected a non-empty measured firing set for a genuinely-firing case"
    assert set(measured) == set(case_expectation.expected_firing)


def test_adv_seed_mode8_corpus_case_is_reconstructed_and_measured_live():
    import segfacet.failure_modes as fm

    case = _manifest_case("mode8_force_overlap")
    assert case["detection"] == "reconstructed_record"

    mode = next(m for m in fm.iter_modes() if m.id == 8)
    assert len(mode.corpus_cases) >= 1
    case_expectation = next(c for c in mode.corpus_cases if c.case_id == "mode8_force_overlap")
    measured = fm.measured_firing(case_expectation)
    assert measured, "expected a non-empty measured firing set for a genuinely-firing case"
    assert set(measured) == set(case_expectation.expected_firing)
