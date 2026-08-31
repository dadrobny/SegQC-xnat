"""Integrity pin for ``src/segfacet/reference/reference_verse_v1.json`` --
relocated here by item 128 (Stage 29, D3) from ``tests/test_098_stray_
components.py``, where it sat under an item-098 name despite protecting
something item 098 has nothing to do with.

``reference_verse_v1.json`` is a **released production artifact**: the
VerSe-derived reference-distribution artifact built from mounted VerSe19
ground truth ([`docs/aide/golden-decision-table.md`](../docs/aide/golden-
decision-table.md) Section 2, disposition ``keep``). It is
**not regenerable in CI** -- nothing in the test suite can rebuild it from
the real cohort -- so the sha256 pin below is the only thing standing between
it and silent corruption. Item 123 rebuilt the artifact from the real VerSe19
cohort under the item-120 held-out estimator and moved the digest; the literal below pins
that item-123-rebuilt state, and only whoever reruns the rebuild against the
real cohort may move it again.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

# Two `.parent` hops from this file resolve to the repo root -- required for
# item 127's committed_artifact_guard classifier to recognise this as a
# repo-root-relative literal chain (see
# committed_artifact_guard._is_file_root_chain). Do not wrap this in a
# helper function: the helper-call form is invisible to both aide check's
# .gitattributes lint and the classifier, which is exactly why relocating
# behind bundled_production_reference_path() would silently drop the pin.
_ARTIFACT = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "segfacet"
    / "reference"
    / "reference_verse_v1.json"
)

# sha256 of the committed reference_verse_v1.json artifact, carried across
# verbatim from tests/test_098_stray_components.py's pre-relocation pin.
# Originally recorded pre-098; item 123 (docs/aide/items/123-recalibrate-
# and-regenerate-downstream-artifacts.md, AC33) rebuilt this artifact from
# the real VerSe19 cohort under the item-120 held-out estimator, so this
# literal pins the item-123 rebuilt state -- golden-decision-table.md's
# signed row for this file is "keep" (not regenerable in CI), so the fence
# stays; only the digest moves, updated by whoever runs the actual rebuild
# against the real cohort (this literal cannot be computed without it).
# tests/test_115_stage26_validation.py::test_ac8_no_hardcoded_literal_fence_
# remains caps the corpus at exactly one such fence, which is this one.
_RELEASED_REFERENCE_VERSE_V1_SHA256 = (
    "2048804f60208a4dea0cbe8d0980e1e6228c68b52b6331375f768254fc73b5da"
)


def test_reference_verse_v1_bytes_unchanged():
    """The released production artifact is byte-identical to its pinned
    (item-123-rebuilt) state."""
    assert _ARTIFACT.name == "reference_verse_v1.json"
    digest = hashlib.sha256(_ARTIFACT.read_bytes()).hexdigest()
    assert digest == _RELEASED_REFERENCE_VERSE_V1_SHA256


def test_reference_verse_v1_still_loads_and_scores_a_case():
    """Liveness check on the shipped artifact: it still loads via the public
    reference API and scores a corpus case without change."""
    from segfacet.config import bundled_default_config
    from segfacet.pipeline import run_qc_with_reference
    from segfacet.reference.artifact import bundled_production_reference
    from segfacet.synth.corpus import load_manifest
    from segfacet.synth.regression import loaded_seg_image

    manifest = load_manifest()
    case = next(c for c in manifest["cases"] if c["case_id"] == "mode6_crop_at_border")
    seg_img = loaded_seg_image(case)
    reference = bundled_production_reference()
    case_result, _block, _delta = run_qc_with_reference(
        seg_img, bundled_default_config(), reference
    )
    bounds_findings = [
        f for f in case_result.findings if f.rule_id == "bounds" and 22 in f.labels
    ]
    assert len(bounds_findings) >= 1
