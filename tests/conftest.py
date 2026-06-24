"""Shared pytest fixtures exposing the synthetic NIfTI cases (item 002).

These are thin wrappers over the framework-agnostic builders in
``tests/synthetic.py``. Every test module — in this item and in later items
(loader, label convention, CLI, empty detection, …) — can request these
fixtures by name without importing ``synthetic`` directly.

In-memory fixtures yield a :class:`synthetic.SyntheticCase` bundle. The
``*_files`` fixtures additionally materialise the case under pytest's
``tmp_path`` and yield ``(scan_path, seg_path)`` so on-disk consumers (e.g. the
CLI in item 006) get real ``.nii.gz`` files to load.
"""

from __future__ import annotations

import pytest

from synthetic import (
    SyntheticCase,
    anisotropic_case,
    empty_case,
    labelled_blocks_case,
)


# --- In-memory case bundles -------------------------------------------------


@pytest.fixture
def labelled_blocks() -> SyntheticCase:
    """Labelled-blocks case: >=3 separated labels, isotropic 1 mm spacing."""
    return labelled_blocks_case()


@pytest.fixture
def empty_labelmap() -> SyntheticCase:
    """Empty case: an all-zero label map (no foreground) + matching scan."""
    return empty_case()


@pytest.fixture
def anisotropic() -> SyntheticCase:
    """Anisotropic case: labelled volume with non-uniform (1,1,3) mm spacing."""
    return anisotropic_case()


# --- On-disk variants (function-scoped, written under tmp_path) -------------


@pytest.fixture
def labelled_blocks_files(labelled_blocks, tmp_path):
    """Write the labelled-blocks case and yield ``(scan_path, seg_path)``."""
    return labelled_blocks.write(tmp_path, suffix=".nii.gz")


@pytest.fixture
def empty_labelmap_files(empty_labelmap, tmp_path):
    """Write the empty case and yield ``(scan_path, seg_path)``."""
    return empty_labelmap.write(tmp_path, suffix=".nii.gz")


@pytest.fixture
def anisotropic_files(anisotropic, tmp_path):
    """Write the anisotropic case and yield ``(scan_path, seg_path)``."""
    return anisotropic.write(tmp_path, suffix=".nii.gz")
