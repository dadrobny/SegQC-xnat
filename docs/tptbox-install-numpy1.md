# Installing FACET + TPTBox 0.7.6 into an existing numpy<2 environment

> Item 094, AC8. This is a **documentation-only** bootstrap procedure, not CI
> automation — CI has no pre-existing numpy<2 environment to install into.
> The real target is a workstation conda env that already has numpy<2 and
> other GPU-stack packages installed (e.g. the `spineps` conda env: Python
> 3.11.15, numpy 1.26.4, monai 1.4.0, previously TPTBox 0.6.1, to be upgraded
> to 0.7.6). If you are doing a plain `pip install -e .[dev]` for this
> repo's own CI/dev workflow, **you do not need anything on this page** — a
> fresh, otherwise-empty venv resolves `tptbox==0.7.6`'s declared
> `numpy>=2.0` marker cleanly (there is nothing else present to conflict
> with it), exactly as this item's own `constraints.txt` regeneration did.

> **Licence metadata in 0.7.6.** The bump closes the AGPL claim only in the
> free-text `License:` field (upstream PR #119: `Apache License Version 2.0,
> January 2004`); the wheel still ships `Classifier: License :: Other/Proprietary
> License`, unchanged from 0.7.5 (both wheels' METADATA read 2026-08-31, item
> 133). A licence scanner or SBOM tool that keys on trove classifiers rather
> than the `License:` field will therefore still report FACET's core dependency
> as proprietary; that residue is upstream's to fix.

## Why the bypass is needed

TPTBox 0.7.6 declares `numpy>=2.0` for `python>=3.11` in its own packaging
metadata. That declaration is **not a real code requirement** — it is a
looser-than-necessary marker, not something TPTBox's implementation actually
needs numpy 2's API surface for. This was verified this session two ways:

- TPTBox's own test suite was run against **numpy 1.26.4** (installed
  `--no-deps` to bypass the declared marker): **417 passed, 4 skipped**, zero
  failures attributable to numpy version.
- An AST scan of TPTBox's source tree for numpy-2-only or numpy-1-removed
  APIs (e.g. `np.float_`, `np.int0`, `np.bool8`, `np.NAN`-style removed
  aliases, or numpy-2-only additions) found **none** in use.

So for an environment that already has numpy<2 pinned by something else
(monai, in the `spineps` case) and cannot be bumped to numpy>=2 without
risking that other package, installing TPTBox 0.7.6 against the existing
numpy<2 is safe in practice, even though `pip install tptbox==0.7.6` alone
would refuse to resolve (or would try to upgrade numpy) in that environment.

## The exact procedure

TPTBox ships as a pure-Python wheel (`tptbox-0.7.6-py3-none-any.whl` — no
compiled extensions, hence no numpy ABI dependency baked into the wheel
itself), so the declared `numpy>=2.0` marker is purely a `pip`-side metadata
gate, not a binary compatibility requirement. Bypassing it with
`pip install --no-deps` is therefore sound: the wheel's actual contents are
identical regardless of which numpy resolves it.

1. **Obtain the pinned release's wheel.** Either build one from the pinned
   `tptbox==0.7.6` source checkout:

   ```bash
   git clone --branch v0.7.6 <tptbox-repo-url> tptbox-src
   cd tptbox-src
   python -m build --wheel        # requires the `build` package
   # -> dist/tptbox-0.7.6-py3-none-any.whl
   ```

   or, equivalently (since the wheel is platform-independent and this
   session confirmed no numpy-version-specific content), download the
   official released wheel directly with `pip download` (no dependency
   resolution, just the artifact):

   ```bash
   pip download tptbox==0.7.6 --no-deps -d ./dist
   # -> dist/tptbox-0.7.6-py3-none-any.whl
   ```

2. **Record the wheel's sha256** so the artifact used is auditable:

   ```bash
   sha256sum dist/tptbox-0.7.6-py3-none-any.whl
   ```

   This session's downloaded wheel hashed to:

   ```
   16fdbcccf4192447897b41825eb2b7249d2e8a860ce4905e7e6c2a18f1fdf5d4  tptbox-0.7.6-py3-none-any.whl
   ```

3. **Install into the target environment with `--no-deps`**, bypassing the
   `numpy>=2.0` marker check entirely (pip only evaluates markers when it is
   also resolving dependencies):

   ```bash
   conda activate spineps   # or whichever existing numpy<2 environment
   pip install --no-deps dist/tptbox-0.7.6-py3-none-any.whl
   ```

   `--no-deps` means none of TPTBox's *other* transitive dependencies
   (SimpleITK, scikit-learn, connected-components-3d, fill-voids, pynrrd,
   dill, requests, matplotlib, joblib, tqdm) are installed or upgraded
   either — install whichever of those the target environment is missing
   separately, at whatever version is already compatible with its existing
   numpy<2 pin (none of them, per the same AST-scan/test-suite check
   applied above, requires numpy>=2 to function correctly at the API level
   TPTBox exercises).

4. **Install FACET itself the same way**, since FACET's own `pyproject.toml`
   now also declares `tptbox==0.7.6` as a core dependency (this item) and
   FACET's `numpy>=1.26,<3` core range is compatible with the target
   environment's numpy<2 pin already — no bypass is needed for FACET's own
   metadata, only for TPTBox's:

   ```bash
   pip install --no-deps -e /path/to/SegFACET
   ```

5. **Verify the install** resolved to the intended versions without numpy
   being touched:

   ```bash
   python -c "import numpy, TPTBox, segfacet; print(numpy.__version__, TPTBox.__version__)"
   ```

   Expect the environment's pre-existing numpy version (e.g. `1.26.4`) and
   `TPTBox` reporting `0.7.6`.

## Scope

This procedure is needed **only** when installing into an environment that
already has numpy<2 pinned by something else and cannot be freely upgraded
(the `spineps` conda env being the motivating case, needed by item 097's
real-SPINEPS validation). It is not part of this repo's own CI or `pip
install -e .[dev]` path, which resolves `tptbox==0.7.6`'s declared
`numpy>=2.0` marker cleanly against an otherwise-empty environment — see
`constraints.txt`, regenerated for this item against a clean venv with no
bypass required.
