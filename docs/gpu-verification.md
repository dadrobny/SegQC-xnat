# GPU capability verification (Stage 10)

Procedure and record for verifying the GPU-accelerated feature-extraction path
(`segqc.backend`, Stage 10) for real, on a machine with an NVIDIA GPU + CUDA
driver. This complements `.github/workflows/ci.yml`'s `verify-environment-gated`
job (which covers pyradiomics and Docker in CI) — GPU hardware isn't available on
standard GitHub-hosted runners, so this path is manual.

**Status: ✅ Verified (2026-07-16).** Ran on a Pascal workstation
(`lihe007-pc`: Quadro P400 / GTX 1080 Ti / 2× Quadro P6000, all **compute
capability 6.1 = sm_61**; driver 580.159.04) against a 24 GB Quadro P6000. The
first-ever CuPy-present run exposed a genuine NEP-50 regression in
`compute_edt_centroids`, fixed under **item 085**; see `docs/aide/progress.md`'s
Environment-Gated Capability Verification table for the record. The steps below
reproduce it.

## Hardware / packaging note (important)

- The cards here are **Pascal, sm_61**. **CUDA 12.x still supports sm_61, but
  CUDA 13 dropped Pascal** — so install the **CUDA-12** CuPy wheel
  (`cupy-cuda12x`), *not* `cupy-cuda13x`. The wheel bundles its own CUDA-12
  runtime, so no system CUDA toolkit is required (the driver, ≥ 525 for CUDA 12,
  is enough; this host has 580.159.04).
- CUDA's default device enumeration is *fastest-first*, which does **not** match
  `nvidia-smi`'s PCI-bus order. Set `CUDA_DEVICE_ORDER=PCI_BUS_ID` if you want
  `CUDA_VISIBLE_DEVICES` indices to line up with `nvidia-smi`.

## Prerequisites

- An NVIDIA GPU with a working driver — confirm `nvidia-smi` prints a device
  table. Check compute capability with
  `nvidia-smi --query-gpu=name,compute_cap --format=csv`.
- The project venv built from a clean interpreter (see `CLAUDE.md`), e.g.
  `/usr/bin/python3 -m venv .venv && .venv/bin/python -m pip install -e ".[dev]"`.

## Steps

1. **Install the CUDA-12 CuPy wheel** into the venv (Linux/macOS shown; on
   Windows use `.venv\Scripts\python`):
   ```
   .venv/bin/python -m pip install cupy-cuda12x
   ```

2. **Confirm CuPy genuinely reaches a Pascal device** — not just driver
   enumeration but a real kernel launch (pin a 24 GB P6000 here):
   ```
   CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES=2 .venv/bin/python -c \
     "import cupy; d=cupy.cuda.Device(); \
      print(cupy.cuda.runtime.getDeviceCount(), d.compute_capability, \
            int((cupy.arange(6)**2).sum()))"
   ```
   Must print a device count ≥ 1, `61`, and `55` (the kernel result), not raise.

3. **Run the GPU-gated test modules** with a JUnit report so skips are visible.
   The CUDA env must be set *before* pytest imports the test modules; the
   simplest reliable way is a tiny in-process runner that sets the env then calls
   `pytest.main([...])` over the Stage-10 modules:
   ```
   tests/test_071_backend.py
   tests/test_072_backend_feature_port.py
   tests/test_073_verdict_equivalence.py
   tests/test_074_benchmark.py
   tests/test_075_cli_backend.py
   tests/test_075_stage10_acceptance.py
   ```
   On a CuPy-present host the `@requires_cupy` equivalence tests **execute**
   (e.g. `test_075_stage10_acceptance.py::test_ac10_gpu_vs_cpu_verdict_identical`,
   `test_072_...::test_ac12_ac13_gpu_cpu_equivalence_spot_check`), and the
   inverse-condition tests (which assert *CuPy-absent* behaviour) self-skip with
   reason "…targets a CuPy-absent host only." Expected result on the P6000:
   **155 passed, 16 skipped, 0 failed**.

4. **Assert no *unexpected* skips**, allow-listing the intentional
   inverse-condition skips by reason substring (the same checker CI uses):
   ```
   .venv/bin/python .github/scripts/assert_no_skips.py gpu-results.xml \
     --allow "CuPy-absent host"
   ```
   This prints `OK: 16 skip(s) found, all allow-listed`. A skip *without* that
   reason means CuPy/the GPU wasn't actually reached (recheck step 2) — it is
   **not** evidence of "gracefully unavailable."

5. **Record it in `docs/aide/progress.md`.** Flip the "GPU-accelerated feature
   extraction" row to `✅ Verified (YYYY-MM-DD, <card, sm_XX>, CuPy <wheel>,
   driver <ver>)` with a one-line note on the command/report that proved it.
   (Done 2026-07-16, item 085.)

## Why this isn't automated in CI

Standard GitHub-hosted runners have no GPU. Automating this would need a
self-hosted runner with an NVIDIA card or a paid GPU CI service — an
infrastructure/cost decision, deliberately left out of `.github/workflows/ci.yml`
rather than faked with a job that can't do what it claims.
