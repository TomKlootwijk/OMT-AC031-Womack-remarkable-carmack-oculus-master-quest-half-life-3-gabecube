# Sources and provenance

The specification labels source-derived vocabulary **S**, explicit mathematical
corrections **C**, and additional implementation choices **D**. These labels do
not promote an AI-generated transcript response into an observed external fact.

## Supplied material

- **S0:** Earlier 42-page transcript, SHA-256
  `76a65e98937648b65c6121bdbe8fd2334e7f35ab7f30fcecf91e4aeb1e4e862e`.
- **S1:** Latest 42-page transcript, SHA-256
  `51a5455b59befbd31b9c2c4f73d96a50186d71605fa8fa338d3339044acdff8c`.
- **S2:** Prior 24-page formalization, SHA-256
  `119fb0589a5f4cacb78bc96d204b3fe7988a95ae9005c9a2d22a53f3ca548b24`.

Page numbers are physical PDF pages, counted from 1. S1 pp.16 and 30 were also
visually inspected for the packed coordinate diagram and operator-flow diagram.
Source PDFs are not republished in this package; this avoids unnecessary
redistribution of unrelated personal details and appended claims.

## Official external documentation

Accessed 13 September 2026. Documentation is used for hardware/API semantics,
not as evidence that atomOS was run on any GPU.

**N1** NVIDIA, CUDA GPU Compute Capability. Desktop GeForce RTX 5070 Ti: 12.0.
https://developer.nvidia.com/cuda/gpus

**N2** NVIDIA, CUDA Toolkit 12.8 Release Notes. Compiler support includes SM_120.
https://docs.nvidia.com/cuda/archive/12.8.0/cuda-toolkit-release-notes/

**N3** NVIDIA, CUDA Runtime API: Texture Object Management. Linear resources,
texture alignment, element limits, element-type reads, object lifetime.
https://docs.nvidia.com/cuda/cuda-runtime-api/group__CUDART__TEXTURE__OBJECT.html

**N4** NVIDIA, CUDA C++ Programming Guide 12.8. Texture memory, device memory,
execution and numerical programming model.
https://docs.nvidia.com/cuda/archive/12.8.0/cuda-c-programming-guide/index.html

**N5** NVIDIA, CUDA C++ Best Practices Guide. Memory spaces, texture coherence and
access-pattern-dependent performance.
https://docs.nvidia.com/cuda/cuda-c-best-practices-guide/

**N6** NVIDIA, Nsight Compute CLI. Section discovery, full profiling and metrics.
https://docs.nvidia.com/nsight-compute/NsightComputeCli/index.html

**N7** Microsoft Learn, User Mode and Kernel Mode.
https://learn.microsoft.com/en-us/windows-hardware/drivers/gettingstarted/user-mode-and-kernel-mode

**N8** Microsoft Learn, Driver Signing Policy.
https://learn.microsoft.com/en-us/windows-hardware/drivers/install/kernel-mode-code-signing-policy--windows-vista-and-later-

**N9** NIST, FIPS 180-4, Secure Hash Standard.
https://csrc.nist.gov/pubs/fips/180-4/upd1/final

**N10** NVIDIA, Compute Sanitizer.
https://docs.nvidia.com/compute-sanitizer/ComputeSanitizer/index.html

**N11** NVIDIA, CUDA Compiler Driver 12.8.
https://docs.nvidia.com/cuda/archive/12.8.0/cuda-compiler-driver-nvcc/index.html

For format-specific linear texture limits, the implementation uses `cudaDeviceGetTexture1DLinearMaxWidth`, not the deprecated `cudaDeviceProp::maxTexture1DLinear` field. See NVIDIA Device Management: https://docs.nvidia.com/cuda/cuda-runtime-api/group__CUDART__DEVICE.html
