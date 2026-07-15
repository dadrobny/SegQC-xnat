# GPU capability verification (Stage 10)

Manual checklist for verifying the GPU-accelerated feature-extraction path
(`segqc.backend`, Stage 10) for real, on a machine that actually has an NVIDIA
GPU and CUDA driver. This complements `.github/workflows/ci.yml`'s
`verify-environment-gated` job, which covers pyradiomics (Stage 8) and Docker
(Stage 9) in CI — GPU hardware isn't available on standard GitHub-hosted
runners, so this path is manual until a GPU-equipped host (self-hosted
runner, cloud GPU instance, or a workstation) is available.

**Not runnable yet.** Stage 10 (items 071–075) is specced but not yet built
(`docs/aide/queue/queue-009.md`). This doc is written now, ahead of that
build, so the verification step isn't reinvented later — treat it as
pending until Stage 10 lands in `docs/aide/progress.md`.

## Prerequisites

- An NVIDIA GPU with a working driver. Confirm with `nvidia-smi` — it must
  print a device table, not "command not found."
- A CUDA toolkit version compatible with a `cupy-cudaXXx` wheel (see
  [CuPy's install guide](https://docs.cupy.dev/en/stable/install.html) for the
  CUDA-version-to-wheel mapping).

## Steps

1. **Install the `gpu` extra**, picking the wheel that matches your CUDA
   version (item 071's `pyproject.toml` `gpu` extra pins a loose `cupy`
   lower bound — you choose the CUDA-matched build):
   ```
   .venv/Scripts/pip install -e .[dev,gpu]
   ```
   or, if the extra's loose pin resolves to the wrong CUDA build, install the
   matched wheel directly first (e.g. `pip install cupy-cuda12x`) then `pip
   install -e .[dev]`.

2. **Confirm CuPy is genuinely importable** before running anything else:
   ```
   .venv/Scripts/python -c "import cupy; print(cupy.cuda.runtime.getDeviceCount())"
   ```
   This must print a number ≥ 1, not raise.

3. **Run the GPU-gated test modules directly**, capturing a JUnit report so
   skips are visible rather than assumed:
   ```
   .venv/Scripts/python -m pytest -v --junitxml=gpu-results.xml ^
     tests/test_071_backend.py ^
     tests/test_072_*.py ^
     tests/test_073_verdict_equivalence.py ^
     tests/test_074_performance_benchmark.py ^
     tests/test_075_stage10_acceptance.py
   ```
   (Adjust filenames once the items are actually built and their test module
   names are known — the queue-009 specs name these modules, but confirm
   against what's actually committed.)

4. **Assert none of the GPU-specific cases skipped**, reusing the same
   zero-skip check CI uses (it takes any JUnit XML, not just CI's):
   ```
   .venv/Scripts/python .github/scripts/assert_no_skips.py gpu-results.xml
   ```
   A skip here means CuPy/the GPU wasn't actually reached by the test run
   (check step 2 again) — it is **not** evidence of "gracefully unavailable,"
   since you've already confirmed the hardware/driver/library are present.

5. **Update `docs/aide/progress.md`'s Environment-Gated Capability
   Verification table.** Flip the "GPU-accelerated feature extraction" row
   from `❓ Unverified` to `✅ Verified (YYYY-MM-DD, <host description, e.g.
   "RTX 4090 workstation, CUDA 12.4">)`, and add a one-line note on which
   command/report proved it (link this doc + the date).

## Why this isn't automated in CI yet

Standard GitHub-hosted runners have no GPU. Automating this would need either
a self-hosted runner with an NVIDIA card or a paid GPU-enabled CI service —
that's an infrastructure/cost decision, not a code change, and is
deliberately left out of `.github/workflows/ci.yml` rather than faked with a
job that can't do what it claims.
