# R17 initial compiled native-code inspection

Review date: 2026-09-15. Scope: static inspection of the initial `sm_120` executable, before the explicit LSYS magnitude-shift optimization. No GPU workload, rebuild, cache-hit measurement or throughput measurement was performed for this audit. The machine-readable counterpart is [r17_native_code_initial.json](r17_native_code_initial.json).

The six fused bodies in this executable have zero reported stack and local-memory allocation, and their disassembly contains no `LDL` or `STL`. Their texture variants contain actual `TLD.LZ` instructions. This supports register retention of the current compiled loop state, while program fetches and chunk-boundary state reads/writes still access memory. It does not establish performance or cache residency.

## Bound evidence

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `C:/aTOMosBuild/r17vm/Release/wqk_run.exe` | 354816 | `202c3dda9ea5e6f4763a89ff1e0827178e6cff91e3ba133bc513f13c50b08d52` |
| [r17_resources_initial.txt](r17_resources_initial.txt) | 3322 | `16075c93af98eb58afaa3eea21931d9e599d967c1e242fe49b2ae7dd8619ed29` |
| [r17_sass_initial.txt](r17_sass_initial.txt) | 2156594 | `b2e9134ee5eba98f70f3179df87bc7a5a3efe5e12426a592720718937f3aa056` |

The executable path is a build location that can subsequently change; the hash identifies the reviewed bytes. The retained reports remain the evidence for this initial build. Source hashes identify the associated source snapshot, rather than constituting a reproducible-build attestation.

| Native source in initial build | Bytes | SHA-256 |
|---|---:|---|
| `include/atomos/tomagi_vm.hpp` | 4176 | `dd59ed86b92fbb122c95cb61f41aa42063b3b01880650aead7e73648c926cb36` |
| `include/atomos/tomagi_feedback.hpp` | 1927 | `af493f2d9de71fea6094170f38433eddbc9133e4f546c5fcbbaef138f4357c31` |
| `cuda/tomagi_vm.cu` | 13797 | `6ba839ac4c4e8aaa16a2928113330569161d3a3dac8e9866915024d9d3d824c1` |
| `cuda/tomagi_feedback.cu` | 9575 | `29828d2245a01cb105a8d61c341e3e55d2781993b0232fea3d77129d0fb91dee` |
| `cuda/tomagi_transition.cuh` | 7138 | `989a3eb698ef802b3de8ad2b5ae0a4cdfa3cf218c890c043f61bd3890760ca7b` |

The last file is preserved byte-for-byte as [tomagi_transition_initial.cuh](tomagi_transition_initial.cuh). The active shared helper subsequently replaces LSYS variable division with a proved exact unsigned magnitude shift; its compiled consequences require a new build and separate audit. The original resource and SASS reports were not overwritten.

## Six fused kernels

| Fused body | Program fetch | Word injection | Registers | Stack bytes | Local bytes | Static TLD sites |
|---|---|---|---:|---:|---:|---:|
| Pure VM batch | Global | — | 53 | 0 | 0 | 0 |
| Pure VM batch | Texture | — | 51 | 0 | 0 | 5 |
| VM + word feedback batch | Global | None | 77 | 0 | 0 | 0 |
| VM + word feedback batch | Texture | None | 77 | 0 | 0 | 5 |
| VM + word feedback batch | Global | `rho/vrho` | 79 | 0 | 0 | 0 |
| VM + word feedback batch | Texture | `rho/vrho` | 81 | 0 | 0 | 5 |

All six also report zero shared memory. The JSON includes exact mangled symbols, starting SASS lines, resource fields, instruction histograms and representative texture/conversion instructions. All thirteen inspected kernels, including the retained reference dispatch, upload expansion and readback helpers, report zero stack/local allocation and contain no `LDL`/`STL`. Both reference VM bodies use 55 registers. The texture reference has five TLD sites; the global reference has none.

The joint evidence is stronger than declaring C++ variables local: the compiled fused loops allocate no local/stack storage and show no corresponding local load/store instructions. This conclusion applies to these embedded `sm_120` bodies. Another compiler, option set, architecture or PTX JIT result can allocate registers or spill differently. Register count alone does not measure achieved occupancy, latency or throughput. NVIDIA documents the resource fields and the `LDL`, `STL` and `TLD` instruction classes in [CUDA Binary Utilities 12.8](https://docs.nvidia.com/cuda/archive/12.8.1/cuda-binary-utilities/index.html#cuobjdump) and its [Blackwell instruction table](https://docs.nvidia.com/cuda/archive/12.8.1/cuda-binary-utilities/index.html#blackwell-instruction-set).

## Texture-object interpretation

The resource dump says `TEXTURE:0 SURFACE:0 SAMPLER:0`. Those metadata counts are not dynamic memory-instruction counters. The source obtains runtime texture-object handles from `ProgramBank` and passes them to `tex1Dfetch<uint4>`; NVIDIA documents this integer-coordinate [texture-object fetch API](https://docs.nvidia.com/cuda/archive/12.8.1/cuda-c-programming-guide/index.html#tex1dfetch). Each fused texture body contains five actual TLD sites, whereas each corresponding global body contains zero. The zero resource field therefore does not establish absence of object-based texture loads.

A static site may execute repeatedly, including during REKEY search, or may not execute on a particular path. Five sites are neither five fetches per logical step nor a hit-rate measurement. This audit makes no claim that every record fits a cache, that all fetches hit, that VRAM bandwidth is saturated, or that this workload outperforms S2.

## Integer semantics and the initial LSYS lowering

The VM source has finite-word integer semantics, but the initial SASS is not composed exclusively of integer-unit mnemonics. `HFMA2` appears in bit-constant materialization. The initial variable-divisor LSYS path contains `I2F.RP`, `MUFU.RCP` and `F2I.FTZ.U32.TRUNC.NTZ`, followed by integer multiply, remainder tests and quotient corrections. In the first pure global body, this sequence occurs around offsets `0x1ee0` through `0x2130` after constructing the clamped power-of-two divisor.

This is compiler lowering of a signed integer division, not a stored floating-point approximation of VM state. Its existence does prevent the stronger claim that no floating-point-unit instruction is used. The initial SASS inspection does not replace the separate arithmetic equivalence tests. The subsequent source optimization expresses this same truncation directly as unsigned magnitude shift and sign restoration; whether the reciprocal instructions disappear, and any performance change, must be checked against the rebuilt executable rather than inferred from this initial report.

## Limits of this evidence

- Static resource and instruction inspection establishes properties of the bound binary, not runtime cache hits or timing.
- Register retention concerns per-lane state inside the fused loop. Initial/final state publication, program records and bank descriptors still use device memory.
- Separate transition tests are needed for correctness; matched workload trials are needed for speed comparisons.
- The hashes bind the reviewed artifact and source bytes. They do not assert a hardware-independent binary, a bit-reproducible toolchain, or an external independent validation.

