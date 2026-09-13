# Execution and privilege contract

Requested hardware: RTX 5070 Ti Laptop GPU, nominal 12 GB GDDR7.
Delivered application: CPU reference plus optional native CUDA texture/global kernels, targeting `sm_120`.

The request also names CPU ring 0. This package does **not** contain a `.sys`, `.ko`, boot module or custom kernel-mode driver. CUDA is dispatched by the user-mode application through the installed NVIDIA driver. `>O<`/ASA is an operator label, not a privilege grant. The project does not rename user-mode code as a ring-0 implementation.

Texture objects provide a read path for data stored in device allocations. Native CUDA instructions execute on the GPU's execution units. Cache placement and eviction are managed by the device; this package does not pin an executable into a texture cache.

The public API has no system-memory, process, networking, device-actuator or real-person identifier input. Output consists of numerical image samples and local verification records.
