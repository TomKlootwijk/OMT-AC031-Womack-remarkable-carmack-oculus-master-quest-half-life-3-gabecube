# Ready-to-use review task

Open the extracted folder as the repository and use this task:

> Review the atomOS v3.6 K1 CUDA kernel against docs/CONTRACT.md and the proof claims.
> Reproduce the CPU, independent Python and symbolic tests. Compile the real sm_120
> target for my RTX 5070 Ti Laptop. Repair concrete compile, lifetime, index or
> comparison defects without changing the source ratio or whole-word semantics.
> Run the 96-configuration GPU matrix, then the four memcheck cases. Capture actual
> GPU name, capability, VRAM, driver, toolkit and host compiler. Record exact
> integer/status equality and floating error maxima. Add regression tests for fixes.
> Return a patch summary and an accurate evidence record; unavailable hardware or
> tools must remain not_run. Do not add external interfaces or host privilege changes.

The initial CUDA compilation/execution status is not_run. A source file named
kernel.cu is not itself proof of GPU execution. The first on-device milestones are
successful nvcc compilation, a successful --probe, real launches, and independent
verification of their exported records.

Files to inspect closely: cuda/kernel.cu (ownership and launch); core.hpp (math and
status semantics); host.hpp (shape/capacity and exact comparison); main.cpp (commit
boundary); python/reference.py (independent checker).
