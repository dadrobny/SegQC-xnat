"""Golden-file JSON report snapshots & determinism harness (item 042).

Reproduces ``segfacet run``'s JSON-report construction for one manifest case
in-process (mirroring ``cli._handle_run`` steps 3-7), canonicalises the
resulting report for byte comparison, and reads/writes the committed golden
corpus under ``tests/corpus/golden/``.

Public surface
--------------
``GOLDEN_DIRNAME``, ``GOLDEN_DIR``, ``VOLATILE_POINTERS``,
``VOLATILE_SENTINEL``, ``build_report_for_case``, ``canonical_json``,
``golden_path``, ``read_golden_text``, ``load_golden``, ``check_case_golden``,
``write_goldens``, ``main``. Additively re-exported from ``segfacet.synth``.

Volatile-field seam
--------------------
The v0 report schema (``report_schema_v0.json``) has ``additionalProperties:
false`` and carries no wall-clock timestamp, absolute path, or tool-version
field -- so the documented volatile-field allow-list, ``VOLATILE_POINTERS``,
is EMPTY for v0. ``canonical_json`` still applies it as a no-op seam so that a
future schema field (e.g. ``generated_at``) can be normalised in exactly one
place without touching every call site.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
from typing import Optional, Sequence, Tuple

from segfacet.config import bundled_default_config
from segfacet.empty import check_empty
from segfacet.pipeline import run_qc
from segfacet.report import serialize_report
from segfacet.synth.corpus import CORPUS_DIR, load_manifest
from segfacet.synth.regression import loaded_seg_image
from segfacet.verdict import Reason, Severity

__all__ = [
    "GOLDEN_DIRNAME",
    "GOLDEN_DIR",
    "VOLATILE_POINTERS",
    "VOLATILE_SENTINEL",
    "build_report_for_case",
    "canonical_json",
    "reports_close",
    "GOLDEN_REL_TOL",
    "GOLDEN_ABS_TOL",
    "golden_path",
    "read_golden_text",
    "load_golden",
    "check_case_golden",
    "write_goldens",
    "main",
]

# --------------------------------------------------------------------------- #
# Module constants
# --------------------------------------------------------------------------- #

#: Name of the golden-snapshots subdirectory under the corpus directory.
GOLDEN_DIRNAME: str = "golden"

#: The committed golden-snapshot directory: tests/corpus/golden.
GOLDEN_DIR: Path = CORPUS_DIR / GOLDEN_DIRNAME

#: Documented volatile-field allow-list applied by :func:`canonical_json`
#: before comparison. EMPTY for report schema v0 -- see the module docstring.
#: Each entry is a tuple of nested dict keys (a "pointer") to normalise.
VOLATILE_POINTERS: Tuple[Tuple[str, ...], ...] = ()

#: Sentinel value a volatile pointer's leaf is replaced with.
VOLATILE_SENTINEL: str = "<normalised>"


# --------------------------------------------------------------------------- #
# Report construction -- mirrors cli._handle_run steps 3-7, in-process
# --------------------------------------------------------------------------- #


def build_report_for_case(case: dict, config=None, corpus_dir: Path = CORPUS_DIR) -> dict:
    """Reproduce ``segfacet run``'s JSON-report construction for one manifest
    *case*, in-process, with ``case_id`` fixed to ``case["case_id"]``.

    Mirrors ``cli._handle_run`` steps 3-7: load the committed seg via the
    Stage 0 loader, run the empty/near-empty check to derive base reasons,
    run the Stage 2-4 pipeline, and serialize the report. The returned dict
    is schema-validated by :func:`segfacet.report.serialize_report` itself.
    """
    seg_img = loaded_seg_image(case, corpus_dir)
    cfg = config or bundled_default_config()

    check_result = check_empty(seg_img, cfg)
    if check_result.is_empty:
        base_reasons = [
            Reason(message=msg, severity=Severity.FAIL)
            for msg in check_result.reasons
        ]
    else:
        base_reasons = [
            Reason(message=msg, severity=Severity.PASS)
            for msg in check_result.reasons
        ]

    case_result, features = run_qc(seg_img, cfg, base_reasons=base_reasons)
    findings = [f.to_dict() for f in case_result.findings]

    return serialize_report(
        case_result.verdict,
        case["case_id"],
        cfg,
        features=features,
        findings=findings,
    )


# --------------------------------------------------------------------------- #
# Canonicalisation
# --------------------------------------------------------------------------- #


def _normalise_pointer(obj: dict, pointer: Tuple[str, ...]) -> None:
    """If *pointer* is fully present in *obj*, set its leaf to
    :data:`VOLATILE_SENTINEL` in place. A no-op if any segment is absent."""
    node = obj
    for key in pointer[:-1]:
        if not isinstance(node, dict) or key not in node:
            return
        node = node[key]
    if isinstance(node, dict) and pointer and pointer[-1] in node:
        node[pointer[-1]] = VOLATILE_SENTINEL


def canonical_json(report: dict, *, volatile_pointers=VOLATILE_POINTERS) -> str:
    """Canonical text form of *report* for byte comparison.

    Deep-copies *report*, replaces the value at each present pointer in
    *volatile_pointers* with :data:`VOLATILE_SENTINEL`, then serialises via
    ``json.dumps(sort_keys=True, indent=2, ensure_ascii=False)`` plus a
    trailing newline. Idempotent.
    """
    normalised = copy.deepcopy(report)
    for pointer in volatile_pointers:
        _normalise_pointer(normalised, tuple(pointer))
    return json.dumps(normalised, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


# --------------------------------------------------------------------------- #
# Cross-platform numeric comparison (item 078)
# --------------------------------------------------------------------------- #
#
# Byte-exact comparison of two report canonicalisations is the right guarantee
# *within a single process on a single platform* (see canonical_json's
# same-platform determinism tests) -- but it is NOT achievable *across*
# platforms for the asymmetric-geometry cases (mode3_inject_islands,
# mode6_crop_at_border, mode8_force_overlap). Those produce irrational-decimal
# floats (off-grid centroids, spline/curvature/EDT values) whose last ~1 ULP
# differs between the platform the committed goldens were generated on and
# another platform, even at identical numpy/scipy versions, because of
# platform BLAS/SIMD/libm rounding. So the *fresh-vs-committed* comparison
# (check_case_golden, item 042 AC9/AC13) uses numeric tolerance rather than
# raw bytes; the same-platform determinism checks (AC4/AC5/AC12) stay byte
# exact. See item 078.

#: Relative tolerance for numeric-leaf comparison in :func:`reports_close`.
GOLDEN_REL_TOL: float = 1e-9

#: Absolute tolerance for numeric-leaf comparison in :func:`reports_close`
#: (governs values near zero, e.g. ``total_curvature_deg`` ~ 1e-14).
GOLDEN_ABS_TOL: float = 1e-12


def reports_close(
    a,
    b,
    *,
    rel_tol: float = GOLDEN_REL_TOL,
    abs_tol: float = GOLDEN_ABS_TOL,
) -> bool:
    """Recursively compare two parsed report structures for equality, with
    numeric leaves compared within tolerance and everything else exactly.

    Rules:

    - ``dict`` -- equal iff the key sets are identical and every value is
      ``reports_close``.
    - ``list`` -- equal iff the lengths match and each pair is
      ``reports_close`` (order-sensitive).
    - ``bool`` -- compared by exact identity, and is **never** treated as a
      number (``True`` is not close to ``1.0``). Checked before the numeric
      branch because ``bool`` is a subclass of ``int``.
    - ``int`` / ``float`` -- compared via
      :func:`math.isclose` with the given tolerances.
    - anything else (``str``, ``None``, ...) -- compared with ``==``.

    Used by :func:`check_case_golden` for the cross-platform fresh-vs-committed
    comparison (item 078). It intentionally does **not** canonicalise or sort
    -- it walks the parsed structures directly.
    """
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, dict) and isinstance(b, dict):
        if a.keys() != b.keys():
            return False
        return all(reports_close(a[k], b[k], rel_tol=rel_tol, abs_tol=abs_tol) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return False
        return all(
            reports_close(x, y, rel_tol=rel_tol, abs_tol=abs_tol) for x, y in zip(a, b)
        )
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(a, b, rel_tol=rel_tol, abs_tol=abs_tol)
    return a == b


# --------------------------------------------------------------------------- #
# Golden storage
# --------------------------------------------------------------------------- #


def golden_path(case_id: str, golden_dir: Path = GOLDEN_DIR) -> Path:
    """``golden_dir / f"{case_id}.json"``."""
    return Path(golden_dir) / f"{case_id}.json"


def read_golden_text(case_id: str, golden_dir: Path = GOLDEN_DIR) -> str:
    """Read the committed golden's UTF-8 text.

    Raises ``FileNotFoundError`` if absent -- a missing golden must fail
    loudly, never silently pass.
    """
    return golden_path(case_id, golden_dir).read_text(encoding="utf-8")


def load_golden(case_id: str, golden_dir: Path = GOLDEN_DIR) -> dict:
    """``json.loads(read_golden_text(...))``."""
    return json.loads(read_golden_text(case_id, golden_dir))


def check_case_golden(
    case: dict,
    config=None,
    golden_dir: Path = GOLDEN_DIR,
    corpus_dir: Path = CORPUS_DIR,
) -> bool:
    """``True`` iff the freshly-built report for *case* matches the committed
    golden **within numeric tolerance** (:func:`reports_close`).

    The comparison is deliberately *not* raw byte-identity: the committed
    goldens encode full-precision floats whose last ~1 ULP differs across
    platforms for the asymmetric-geometry cases, so a fresh build on a
    different platform than the one the goldens were generated on would fail a
    byte comparison despite being numerically identical (item 078). Numeric
    leaves are compared with tolerance; structure, keys, strings, bools, and
    ordering are compared exactly, so a genuine difference (a changed verdict,
    a new/removed finding, a meaningfully different feature value) is still
    caught. Propagates ``FileNotFoundError`` when the golden is missing (does
    not swallow it)."""
    fresh = build_report_for_case(case, config, corpus_dir)
    committed = json.loads(read_golden_text(case["case_id"], golden_dir))
    return reports_close(fresh, committed)


def write_goldens(
    dest: Path = GOLDEN_DIR, config=None, corpus_dir: Path = CORPUS_DIR
) -> list:
    """Regenerate one ``dest/<case_id>.json`` per manifest case.

    Deterministic: writes canonical-JSON UTF-8 bytes via ``write_bytes`` so
    line endings are exactly ``\\n`` on every supported Python/platform.
    Returns the list of written paths.
    """
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)

    written = []
    for case in load_manifest()["cases"]:
        text = canonical_json(build_report_for_case(case, config, corpus_dir))
        path = golden_path(case["case_id"], dest)
        path.write_bytes(text.encode("utf-8"))
        written.append(path)
    return written


# --------------------------------------------------------------------------- #
# CLI entry point
# --------------------------------------------------------------------------- #


def main(argv: Optional[Sequence[str]] = None) -> int:
    """``python -m segfacet.synth.golden [--out DIR]`` -- the one-command
    golden-update path (default ``--out`` == :data:`GOLDEN_DIR`).

    Returns ``0`` on success.
    """
    parser = argparse.ArgumentParser(
        prog="segfacet.synth.golden",
        description="Regenerate the committed golden-file JSON report snapshots.",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=str(GOLDEN_DIR),
        help="Destination directory (default: the committed tests/corpus/golden).",
    )
    args = parser.parse_args(argv)

    out = args.out
    written = write_goldens(Path(out))
    print(f"Wrote {len(written)} goldens to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
