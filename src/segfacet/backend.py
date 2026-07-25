"""GPU/CPU compute-backend selection layer (item 071).

FACET is **CPU-only by default and zero-required-GPU-dependency**: the
tool installs and runs its full test suite with nothing beyond the core
scientific stack (``numpy``/``scipy``/...). This module adds a thin
*selection* layer on top of that: it decides, at runtime, whether array
operations should run through NumPy (CPU) or CuPy (GPU), without ever making
CuPy a required import.

Precedence and resolution
--------------------------
A concrete backend name (``"cpu"`` or ``"gpu"``) is resolved from, in order:

1. An explicit ``override`` argument (e.g. the future ``segfacet run --backend``
   flag from item 075) -- used whenever it is non-``None`` and non-empty after
   stripping whitespace.
2. The ``SEGFACET_BACKEND`` environment variable -- used when ``override`` is
   absent; an empty/whitespace-only value is treated as unset.
3. The default token ``"auto"`` when neither of the above is set.

Tokens are matched case-insensitively after ``.strip().lower()``. The token
``"auto"`` resolves to ``"gpu"`` when CuPy is genuinely importable, else
``"cpu"``. Requesting ``"gpu"`` explicitly (via override or env var) when CuPy
is unavailable raises :class:`FacetBackendError` -- a clean, actionable
message, never a bare ``ImportError`` traceback.

Dynamic probe, by design
--------------------------
:func:`cupy_available` performs a guarded ``import cupy`` *inside* the
function body on every call, honouring the live state of ``sys.modules``,
rather than caching a boolean at module-import time (contrast
``segfacet.features.radiomics``'s module-scope-cached ``pyradiomics_available``
pattern). This is deliberate: it is what makes the selection logic fully
unit-testable on a GPU-less host, by injecting/removing a ``cupy`` entry in
``sys.modules`` between calls within a single process, without any real GPU
or CuPy install.

Scope fence -- what this module is NOT
-----------------------------------------
This module contains **only** selection/resolution logic and the ``Backend``
handle. It does not:

- Migrate or touch any feature-extraction code (``features/geometry.py``,
  ``components.py``, ``centroids.py``, ``spline.py``, ...) -- routing those
  through ``Backend.xp`` is item 072's job.
- Add a CLI surface (``segfacet run --backend ...``) -- that is item 075's job;
  this module stops at the ``SEGFACET_BACKEND`` env var and the programmatic
  ``override`` argument that the future flag will feed.
- Execute or verify anything against a real GPU/CuPy install -- "available"
  here means only "``cupy`` is importable"; genuine device/execution
  verification is items 073/075's GPU-gated concern.
- Touch the pipeline, report, verdict, or schema in any way.
"""

from __future__ import annotations

import functools
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import numpy

__all__ = [
    "BACKEND_CPU",
    "BACKEND_GPU",
    "BACKEND_AUTO",
    "ENV_VAR",
    "FacetBackendError",
    "Backend",
    "cupy_available",
    "resolve_backend_choice",
    "backend_name",
    "get_backend",
]


# ---- Constants ---------------------------------------------------------- #

BACKEND_CPU = "cpu"
BACKEND_GPU = "gpu"
BACKEND_AUTO = "auto"

#: Name of the environment variable used to select a backend when no
#: explicit ``override`` argument is supplied (see module docstring for the
#: full precedence order).
ENV_VAR = "SEGFACET_BACKEND"

#: All tokens accepted by :func:`resolve_backend_choice` (post
#: ``.strip().lower()`` normalisation).
_VALID_TOKENS = frozenset({BACKEND_CPU, BACKEND_GPU, BACKEND_AUTO})


# ---- Exception ----------------------------------------------------------- #

class FacetBackendError(Exception):
    """Raised when a backend cannot be resolved or the resolved choice is
    unusable on this host.

    Covers two cases:
    - An unrecognised backend token (neither ``cpu``, ``gpu``, nor ``auto``).
    - GPU explicitly requested (override or ``SEGFACET_BACKEND``) while ``cupy``
      is not importable -- the message names the ``gpu`` extra as the
      remediation rather than letting a bare ``ImportError`` propagate.
    """


# ---- Capability probe ----------------------------------------------------- #

def cupy_available() -> bool:
    """Return whether ``cupy`` is importable right now.

    Performs a guarded ``import cupy`` *inside* this function on every call
    (never cached at module scope) so the result always reflects the current
    state of ``sys.modules`` -- see the module docstring's "Dynamic probe, by
    design" section. Never raises; any failure to import is treated as
    "unavailable".
    """
    try:
        import cupy  # noqa: F401
    except ImportError:
        return False
    return True


# ---- Backend handle -------------------------------------------------------- #

@dataclass(frozen=True)
class Backend:
    """Immutable handle describing a resolved compute backend.

    Attributes:
        name: Concrete backend name, ``"cpu"`` or ``"gpu"``.
        is_gpu: ``True`` for the GPU backend, ``False`` for CPU.
        xp: The array module to route operations through -- the ``numpy``
            module for CPU, the ``cupy`` module for GPU. Named ``xp`` per the
            common NumPy/CuPy-interchangeable-array-module convention.
        ndimage: The ndimage module to route ``label`` /
            ``distance_transform_edt`` / ``gaussian_filter`` calls through --
            ``scipy.ndimage`` for CPU, ``cupyx.scipy.ndimage`` for GPU. Added
            by item 072. Exposed as a cached property backed by
            ``_ndimage_loader`` so that ``import cupyx.scipy.ndimage`` (which
            genuinely requires a CuPy install, unlike the bare ``import
            cupy`` used for capability probing) happens lazily -- only the
            first time ``.ndimage`` is actually accessed on a GPU backend --
            rather than eagerly inside :func:`get_backend` just to construct
            the handle. This keeps ``get_backend(override="gpu")`` itself
            working under a host/test double that stubs ``cupy`` but not
            ``cupyx`` (see ``tests/test_071_backend.py``'s ``fake_cupy``
            fixture, which never touches ``.ndimage``).
    """

    name: str
    is_gpu: bool
    xp: Any
    _ndimage_loader: Callable[[], Any] = field(repr=False, compare=False)

    @functools.cached_property
    def ndimage(self) -> Any:
        """The ndimage module for this backend, imported on first access.

        Direct instance-``__dict__`` caching via ``functools.cached_property``
        works even though :class:`Backend` is a frozen dataclass: the cache
        write bypasses ``__setattr__`` (and thus ``FrozenInstanceError``) by
        writing straight into ``instance.__dict__``.
        """
        return self._ndimage_loader()


# ---- Resolution ------------------------------------------------------------ #

def resolve_backend_choice(override: Optional[str] = None) -> str:
    """Resolve the effective backend name (``"cpu"`` or ``"gpu"``).

    Precedence: explicit ``override`` (when non-``None`` and non-empty after
    stripping whitespace) > the ``SEGFACET_BACKEND`` environment variable (when
    non-empty after stripping) > the default token ``"auto"``. Tokens are
    matched case-insensitively after ``.strip().lower()``.

    Raises:
        FacetBackendError: if the effective token is not one of ``cpu``,
            ``gpu``, ``auto``; or if it resolves to ``gpu`` (directly, or via
            ``auto`` -- though ``auto`` only ever resolves to ``gpu`` when
            CuPy is available) while ``cupy`` is not importable.
    """
    raw = override if override is not None and override.strip() else None
    if raw is None:
        raw = os.environ.get(ENV_VAR)
    token = (raw or "").strip().lower()
    if not token:
        token = BACKEND_AUTO

    if token not in _VALID_TOKENS:
        raise FacetBackendError(
            f"Invalid FACET backend {token!r}. "
            f"Valid values are: {BACKEND_CPU!r}, {BACKEND_GPU!r}, {BACKEND_AUTO!r}."
        )

    if token == BACKEND_AUTO:
        resolved = BACKEND_GPU if cupy_available() else BACKEND_CPU
    else:
        resolved = token

    if resolved == BACKEND_GPU and not cupy_available():
        raise FacetBackendError(
            "GPU backend requested but the 'cupy' package is not importable. "
            "Install a CUDA-matched CuPy build via the optional 'gpu' extra "
            "(e.g. `pip install segfacet[gpu]` plus a CUDA-matched cupy-cudaXXx "
            "wheel), or select the 'cpu'/'auto' backend instead."
        )

    return resolved


def backend_name(override: Optional[str] = None) -> str:
    """Return the resolved backend name (``"cpu"`` or ``"gpu"``).

    Thin wrapper around :func:`resolve_backend_choice`; propagates
    :class:`FacetBackendError` for invalid tokens or an unavailable forced-GPU
    request.
    """
    return resolve_backend_choice(override=override)


def get_backend(override: Optional[str] = None) -> Backend:
    """Resolve and build the concrete :class:`Backend` handle.

    Resolves the effective backend name via :func:`resolve_backend_choice`,
    then builds a :class:`Backend` bound to the corresponding array module.
    The ``cupy`` import happens only on the GPU path -- the CPU path never
    imports ``cupy``.

    Raises:
        FacetBackendError: propagated from :func:`resolve_backend_choice`.
    """
    resolved = resolve_backend_choice(override=override)
    if resolved == BACKEND_CPU:
        import scipy.ndimage

        return Backend(
            name=BACKEND_CPU,
            is_gpu=False,
            xp=numpy,
            _ndimage_loader=lambda: scipy.ndimage,
        )

    import cupy

    def _load_gpu_ndimage() -> Any:
        # Deferred: only imported the first time `.ndimage` is actually
        # accessed on a GPU backend, not eagerly here -- `cupyx` genuinely
        # requires a real CuPy install (unlike the bare `import cupy` above,
        # which a sys.modules stub can satisfy for capability probing/tests).
        import cupyx.scipy.ndimage

        return cupyx.scipy.ndimage

    return Backend(name=BACKEND_GPU, is_gpu=True, xp=cupy, _ndimage_loader=_load_gpu_ndimage)
