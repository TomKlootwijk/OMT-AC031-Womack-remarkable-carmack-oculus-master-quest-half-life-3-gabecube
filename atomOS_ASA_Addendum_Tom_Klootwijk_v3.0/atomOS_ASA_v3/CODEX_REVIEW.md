# Codex verification and repair brief

## Objective
Verify and repair this ASA addendum on an NVIDIA GeForce RTX 5070 Ti Laptop GPU with nominal 12 GB GDDR7. Keep the source vocabulary, documented operator sequence, numerical definitions and independent oracle. Produce a patch plus test evidence, not just a review narrative.

## First pass
Read `AGENTS.md`, `README.md`, `docs/PROFILES.md`, `docs/SOURCE_MAP.md`, and `docs/BUILD_STATUS.md`. Run `python scripts/validate.py` and preserve the generated logs. Inspect the shared core, then inspect the independent Python oracle without importing the C++ implementation into it.

## GPU acceptance
Build and run `python scripts/validate.py --gpu --sanitizer` on the laptop. Inspect `device.log` for the actual GPU name, compute capability, available memory, runtime and driver version. Keep the default `120-real;120-virtual` target unless the actual device requires a documented change.

The acceptance set is:
1. Native CUDA compilation succeeds with the installed supported host compiler.
2. Texture and direct global-load paths agree with CPU flags and logical keys exactly, and values within 2e-6.
3. Both explicit storage layouts pass the independent Python oracle.
4. Zero, one, 257, 4097 and 65536 input samples behave correctly; no zero-block launch occurs.
5. Rectangular 8-aligned dictionaries, angular seams, half-open radial ends and aperture boundaries behave as specified.
6. Invalid dimensions, insufficient VRAM, invalid device selection and nonempty output directories fail cleanly.
7. Compute Sanitizer memcheck, initcheck, racecheck and synccheck report no errors for the requested runs.
8. Read-only texture buffers live through completion and are destroyed in the right order.

## Focused edge cases
Test `alpha=0`, `alpha=pi/2`, hinge endpoints, nonzero axis, positive/negative warp, the maximum admitted angular warp, and values adjacent to a LUT boundary using `nextafter`. Keep logical indices exact even when numerical values use tolerances. Add a minimal repro before fixing each defect.

## Performance work only after correctness
Warm up and run repeated identical workloads. Record native device memory, toolkit/compiler versions, launch size, elapsed kernel time and end-to-end time separately. Compare row-major and Morton8, and texture versus global reads; do not presume which wins. Do not disable system driver protections or watchdogs. The default implementation uses binary64 coordinate arithmetic and binary32 tables; a lower-precision variant is a new profile, not a silent replacement.

## Review output
Write `CODEX_FINDINGS.md` with defects, changed files and rationale. Store fresh logs and a status JSON under `local_validation/` or another new directory. Distinguish executed, failed and unavailable steps. Update the PDF source only for demonstrated changes to the declared contract. Recompute the package manifest only when publishing a new edition.

## Ready-to-paste task
> Read AGENTS.md and CODEX_REVIEW.md. Verify and fix this ASA v3 numerical image kernel on my RTX 5070 Ti Laptop GPU. Preserve operator order and source traceability. Build CPU and CUDA, run the independent oracle and Compute Sanitizer, add regression tests for every fix, and provide a patch with actual build/device logs. Do not replace unavailable checks with a claim of success.
