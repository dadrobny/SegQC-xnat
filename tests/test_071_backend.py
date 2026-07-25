"""Tests for the GPU/CPU backend abstraction module (item 071).

Covers all 15 Acceptance Criteria plus adversarial/edge-case inputs, per
``docs/aide/items/071-gpu-cpu-backend-abstraction.md``. ``cupy`` is never
installed on this host, so every GPU-present/GPU-absent behaviour is proven by
mocking ``sys.modules["cupy"]`` -- never a real ``import cupy``:

- **present**: ``monkeypatch.setitem(sys.modules, "cupy", stub)`` injects a
  stub module object (the ``fake_cupy`` fixture below), so the guarded
  ``import cupy`` inside ``cupy_available()``/``get_backend()`` succeeds and
  binds to that exact stub.
- **absent**: ``sys.modules["cupy"] = None`` makes the guarded import raise
  ``ImportError`` (Python's import machinery treats a ``None`` sentinel in
  ``sys.modules`` as "module known absent"), modelling absence robustly even
  on a host where CuPy happens to be genuinely installed.

``SEGFACET_BACKEND`` is always explicitly set/cleared via
``monkeypatch.setenv``/``delenv`` so tests are hermetic and order-independent.

All tests are deterministic, CPU-only, and portable (no network, no absolute
paths, no real GPU).
"""

from __future__ import annotations

import sys

import numpy as np
import pytest

from segfacet.backend import (
    BACKEND_AUTO,
    BACKEND_CPU,
    BACKEND_GPU,
    ENV_VAR,
    Backend,
    FacetBackendError,
    backend_name,
    cupy_available,
    get_backend,
    resolve_backend_choice,
)


# =========================================================================== #
# Fixtures / helpers
# =========================================================================== #


@pytest.fixture
def fake_cupy(monkeypatch):
    """Inject a stub module object into sys.modules["cupy"] to model
    CuPy being importable/"present", without a real CuPy install."""
    import types

    stub = types.ModuleType("cupy")
    monkeypatch.setitem(sys.modules, "cupy", stub)
    return stub


def _make_cupy_absent(monkeypatch):
    """Model CuPy being genuinely absent: the sentinel makes any guarded
    ``import cupy`` raise ImportError, robust even if CuPy happens to be
    installed on this host."""
    monkeypatch.setitem(sys.modules, "cupy", None)


@pytest.fixture
def cupy_absent(monkeypatch):
    _make_cupy_absent(monkeypatch)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Hermetic default: SEGFACET_BACKEND unset unless a test sets it."""
    monkeypatch.delenv(ENV_VAR, raising=False)


# =========================================================================== #
# AC1  Module imports GPU-free
# =========================================================================== #


def test_ac1_module_imports_without_cupy(monkeypatch):
    """import segfacet.backend succeeds with cupy modelled absent -- no
    ImportError, and the module does not depend on cupy at import time."""
    _make_cupy_absent(monkeypatch)
    import importlib

    mod = importlib.import_module("segfacet.backend")
    assert mod is not None


def test_ac1_public_api_names_present():
    import segfacet.backend as mod

    for name in (
        "FacetBackendError",
        "Backend",
        "cupy_available",
        "get_backend",
        "backend_name",
        "resolve_backend_choice",
        "BACKEND_CPU",
        "BACKEND_GPU",
        "BACKEND_AUTO",
        "ENV_VAR",
    ):
        assert hasattr(mod, name), name
        assert name in mod.__all__


def test_ac1_constants_have_expected_values():
    assert BACKEND_CPU == "cpu"
    assert BACKEND_GPU == "gpu"
    assert BACKEND_AUTO == "auto"
    assert ENV_VAR == "SEGFACET_BACKEND"


# =========================================================================== #
# AC2  Capability probe reports absent
# =========================================================================== #


def test_ac2_cupy_available_false_when_absent(cupy_absent):
    result = cupy_available()
    assert result is False


def test_ac2_cupy_available_does_not_raise_when_absent(cupy_absent):
    cupy_available()  # must not raise


# =========================================================================== #
# AC3  Capability probe reports present
# =========================================================================== #


def test_ac3_cupy_available_true_when_present(fake_cupy):
    assert cupy_available() is True


# =========================================================================== #
# AC4  Auto-detect falls back to CPU
# =========================================================================== #


def test_ac4_auto_detect_falls_back_to_cpu(cupy_absent):
    assert backend_name() == "cpu"


# =========================================================================== #
# AC5  Auto-detect selects GPU when CuPy present
# =========================================================================== #


def test_ac5_auto_detect_selects_gpu_when_present(fake_cupy):
    assert backend_name() == "gpu"


# =========================================================================== #
# AC6  Env override forces CPU over an available GPU
# =========================================================================== #


def test_ac6_env_cpu_wins_over_available_gpu(fake_cupy, monkeypatch):
    monkeypatch.setenv(ENV_VAR, "cpu")
    assert backend_name() == "cpu"


# =========================================================================== #
# AC7  Forcing GPU without CuPy raises a clear, non-traceback error
# =========================================================================== #


def test_ac7_env_gpu_absent_raises_segfacet_backend_error(cupy_absent, monkeypatch):
    monkeypatch.setenv(ENV_VAR, "gpu")
    with pytest.raises(FacetBackendError) as excinfo:
        get_backend()
    message = str(excinfo.value)
    assert message
    assert "cupy" in message.lower() or "gpu" in message.lower()


def test_ac7_override_gpu_absent_raises_segfacet_backend_error(cupy_absent):
    with pytest.raises(FacetBackendError) as excinfo:
        get_backend(override="gpu")
    message = str(excinfo.value)
    assert message


def test_ac7_backend_name_also_raises_for_forced_gpu_absent(cupy_absent):
    with pytest.raises(FacetBackendError):
        backend_name(override="gpu")


def test_ac7_raised_type_is_not_bare_import_error(cupy_absent):
    """The typed FacetBackendError must not itself be a bare ImportError."""
    with pytest.raises(FacetBackendError) as excinfo:
        get_backend(override="gpu")
    assert not isinstance(excinfo.value, ImportError)


def test_ac7_message_mentions_remediation(cupy_absent):
    with pytest.raises(FacetBackendError) as excinfo:
        get_backend(override="gpu")
    lowered = str(excinfo.value).lower()
    assert "gpu" in lowered
    assert "extra" in lowered or "install" in lowered or "cupy" in lowered


# =========================================================================== #
# AC8  Explicit argument beats the env var
# =========================================================================== #


def test_ac8_explicit_override_beats_env_var(fake_cupy, monkeypatch):
    monkeypatch.setenv(ENV_VAR, "gpu")
    assert backend_name(override="cpu") == "cpu"


def test_ac8_get_backend_explicit_override_beats_env_var(fake_cupy, monkeypatch):
    monkeypatch.setenv(ENV_VAR, "gpu")
    backend = get_backend(override="cpu")
    assert backend.name == "cpu"


# =========================================================================== #
# AC9  Invalid override token is rejected
# =========================================================================== #


def test_ac9_invalid_token_via_env_raises(monkeypatch):
    monkeypatch.setenv(ENV_VAR, "turbo")
    with pytest.raises(FacetBackendError) as excinfo:
        backend_name()
    message = str(excinfo.value).lower()
    assert "cpu" in message
    assert "gpu" in message
    assert "auto" in message


def test_ac9_invalid_token_via_argument_raises():
    with pytest.raises(FacetBackendError) as excinfo:
        backend_name(override="turbo")
    message = str(excinfo.value).lower()
    assert "cpu" in message
    assert "gpu" in message
    assert "auto" in message


def test_ac9_invalid_token_not_bare_exception_type():
    with pytest.raises(FacetBackendError):
        resolve_backend_choice(override="turbo")


# =========================================================================== #
# AC10  CPU Backend handle shape
# =========================================================================== #


def test_ac10_cpu_backend_handle_shape():
    backend = get_backend(override="cpu")
    assert isinstance(backend, Backend)
    assert backend.name == "cpu"
    assert backend.is_gpu is False
    assert backend.xp is np


# =========================================================================== #
# AC11  GPU Backend handle shape
# =========================================================================== #


def test_ac11_gpu_backend_handle_shape(fake_cupy):
    backend = get_backend(override="gpu")
    assert isinstance(backend, Backend)
    assert backend.name == "gpu"
    assert backend.is_gpu is True
    assert backend.xp is fake_cupy


# =========================================================================== #
# AC12  Token normalisation
# =========================================================================== #


def test_ac12_env_whitespace_and_mixed_case_normalised_to_gpu(fake_cupy, monkeypatch):
    monkeypatch.setenv(ENV_VAR, " GPU ")
    assert backend_name() == "gpu"


@pytest.mark.parametrize("empty_value", ["", "   "])
def test_ac12_empty_or_whitespace_env_treated_as_unset(cupy_absent, monkeypatch, empty_value):
    monkeypatch.setenv(ENV_VAR, empty_value)
    assert backend_name() == "cpu"


def test_ac12_override_whitespace_and_mixed_case_normalised(fake_cupy):
    assert backend_name(override=" GPU ") == "gpu"


def test_ac12_resolve_backend_choice_matches_backend_name():
    assert resolve_backend_choice(override="cpu") == "cpu"


# =========================================================================== #
# AC13  Probe reflects current import state (not import-time cache)
# =========================================================================== #


def test_ac13_probe_re_evaluates_absent_to_present(monkeypatch):
    _make_cupy_absent(monkeypatch)
    first = cupy_available()

    import types

    stub = types.ModuleType("cupy")
    monkeypatch.setitem(sys.modules, "cupy", stub)
    second = cupy_available()

    assert first is False
    assert second is True
    assert first != second


def test_ac13_probe_re_evaluates_present_to_absent(fake_cupy, monkeypatch):
    first = cupy_available()
    _make_cupy_absent(monkeypatch)
    second = cupy_available()

    assert first is True
    assert second is False
    assert first != second


def test_ac13_absent_sentinel_genuinely_raises_on_guarded_import(cupy_absent):
    """Non-vacuous check: the sys.modules[None] sentinel actually makes a
    guarded ``import cupy`` raise ImportError, so AC2/AC13's "absent" tests
    are proving something real."""
    with pytest.raises(ImportError):
        import cupy  # noqa: F401


# =========================================================================== #
# AC14  No GPU library in core dependencies
# =========================================================================== #


def _load_pyproject():
    try:
        import tomllib  # Python 3.11+
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef]
    with open("pyproject.toml", "rb") as f:
        return tomllib.load(f)


def test_ac14_core_dependencies_exclude_cupy_and_cucim():
    data = _load_pyproject()
    core_deps = " ".join(data["project"].get("dependencies", [])).lower()
    assert "cupy" not in core_deps
    assert "cucim" not in core_deps


# =========================================================================== #
# AC15  Optional gpu extra present
# =========================================================================== #


def test_ac15_optional_gpu_extra_declares_cupy():
    data = _load_pyproject()
    optional = data["project"].get("optional-dependencies", {})
    assert "gpu" in optional, "expected a `gpu` optional extra"
    gpu_extra = " ".join(optional["gpu"]).lower()
    assert "cupy" in gpu_extra


def test_ac15_gpu_extra_excludes_cucim():
    """A3: item 072 needs no cucim -- the gpu extra ships cupy only."""
    data = _load_pyproject()
    optional = data["project"].get("optional-dependencies", {})
    gpu_extra = " ".join(optional.get("gpu", [])).lower()
    assert "cucim" not in gpu_extra


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_explicit_override_auto_behaves_like_default_absent(cupy_absent):
    assert backend_name(override="auto") == "cpu"


def test_adv_explicit_override_auto_behaves_like_default_present(fake_cupy):
    assert backend_name(override="auto") == "gpu"


def test_adv_explicit_override_auto_beats_conflicting_env(cupy_absent, monkeypatch):
    monkeypatch.setenv(ENV_VAR, "gpu")
    # explicit override="auto" still wins over the env var per precedence,
    # and auto correctly falls back to cpu since cupy is absent.
    assert backend_name(override="auto") == "cpu"


def test_adv_invalid_token_env_and_argument_both_raise_with_message(monkeypatch):
    monkeypatch.setenv(ENV_VAR, "turbo")
    with pytest.raises(FacetBackendError):
        backend_name()
    monkeypatch.delenv(ENV_VAR, raising=False)
    with pytest.raises(FacetBackendError):
        backend_name(override="turbo")


def test_adv_force_gpu_absent_env_and_argument_both_raise(cupy_absent, monkeypatch):
    monkeypatch.setenv(ENV_VAR, "gpu")
    with pytest.raises(FacetBackendError):
        get_backend()
    monkeypatch.delenv(ENV_VAR, raising=False)
    with pytest.raises(FacetBackendError):
        get_backend(override="gpu")


def test_adv_determinism_repeated_get_backend_calls_cpu():
    b1 = get_backend(override="cpu")
    b2 = get_backend(override="cpu")
    assert b1.name == b2.name
    assert b1.is_gpu == b2.is_gpu
    assert b1.xp is b2.xp


def test_adv_determinism_repeated_get_backend_calls_gpu(fake_cupy):
    b1 = get_backend(override="gpu")
    b2 = get_backend(override="gpu")
    assert b1.name == b2.name
    assert b1.is_gpu == b2.is_gpu
    assert b1.xp is b2.xp


def test_adv_backend_is_frozen_dataclass():
    import dataclasses

    backend = get_backend(override="cpu")
    assert dataclasses.is_dataclass(backend)
    with pytest.raises(dataclasses.FrozenInstanceError):
        backend.name = "gpu"  # type: ignore[misc]
